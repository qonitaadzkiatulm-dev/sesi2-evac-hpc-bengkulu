"""Loader data nyata -> World (hanya butuh numpy, tanpa GDAL/rasterio).

Folder data berisi 4 berkas:
  config.json      {"bbox": [lon_min, lat_min, lon_max, lat_max], "cell_m": 10,
                    "sea_below_m": 0.0, "max_runup_m": 10.0, "high_ground_is_safe": true}
  dem.asc          DEM format ESRI ASCII Grid (EPSG:4326, derajat). Ekspor dari QGIS/GDAL.
  roads.geojson    LineString/MultiLineString jalan (mis. dari OpenStreetMap).
  shelters.csv     kolom: name,lat,lon  (titik tempat evakuasi; di-snap ke jalan terdekat)

Asumsi: sel DEM kosong/di luar DEM dianggap laut; penduduk berjalan hanya di jalan.
"""
import csv
import json
from pathlib import Path

import numpy as np

from .model import INF, World, bfs_from


def read_asc(path):
    """Baca ESRI ASCII grid -> (data[nrows,ncols], xll, yll, cellsize, nodata)."""
    with open(path) as f:
        hdr = {}
        for _ in range(6):
            k, v = f.readline().split()
            hdr[k.lower()] = float(v)
        data = np.loadtxt(f, ndmin=2)
    cs = hdr["cellsize"]
    xll = hdr["xllcorner"] if "xllcorner" in hdr else hdr["xllcenter"] - cs / 2
    yll = hdr["yllcorner"] if "yllcorner" in hdr else hdr["yllcenter"] - cs / 2
    return data, xll, yll, cs, hdr.get("nodata_value", -9999.0)


def _geometry(cfg):
    lon0, lat0, lon1, lat1 = cfg["bbox"]
    cell = float(cfg.get("cell_m", 10.0))
    dlat = cell / 111320.0
    dlon = cell / (111320.0 * np.cos(np.radians((lat0 + lat1) / 2)))
    h = int(np.ceil((lat1 - lat0) / dlat))
    w = int(np.ceil((lon1 - lon0) / dlon))
    return lon0, lat1, dlon, dlat, h, w


def sample_dem(dem_path, lon0, lat1, dlon, dlat, h, w):
    """Elevasi di pusat tiap sel grid (NaN bila di luar/di nodata DEM)."""
    data, xll, yll, cs, nodata = read_asc(dem_path)
    nrows, ncols = data.shape
    ys, xs = np.mgrid[0:h, 0:w]
    lon = lon0 + (xs + 0.5) * dlon
    lat = lat1 - (ys + 0.5) * dlat
    col = np.floor((lon - xll) / cs).astype(int)
    row = np.floor((yll + nrows * cs - lat) / cs).astype(int)
    ok = (col >= 0) & (col < ncols) & (row >= 0) & (row < nrows)
    elev = np.full((h, w), np.nan)
    vals = data[row[ok], col[ok]]
    vals = np.where(vals == nodata, np.nan, vals)
    elev[ok] = vals
    return elev


def rasterize_roads(geojson, lon0, lat1, dlon, dlat, h, w):
    """Gambar garis jalan ke grid, tersambung 4-arah (tanpa celah diagonal)."""
    road = np.zeros((h, w), dtype=bool)

    def mark(cx, cy):
        m = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
        road[cy[m], cx[m]] = True

    lines = []
    for ft in geojson.get("features", []):
        g = ft.get("geometry") or {}
        if g.get("type") == "LineString":
            lines.append(g["coordinates"])
        elif g.get("type") == "MultiLineString":
            lines.extend(g["coordinates"])
    for line in lines:
        pts = np.array([[(lo - lon0) / dlon, (lat1 - la) / dlat] for lo, la, *_ in line])
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            n = max(1, int(np.ceil(max(abs(x1 - x0), abs(y1 - y0)) * 2)))
            t = np.linspace(0, 1, n + 1)
            cx = np.floor(x0 + (x1 - x0) * t).astype(int)
            cy = np.floor(y0 + (y1 - y0) * t).astype(int)
            mark(cx, cy)
            diag = (cx[1:] != cx[:-1]) & (cy[1:] != cy[:-1])
            mark(cx[1:][diag], cy[:-1][diag])  # sel penyambung sudut
    return road


def load_world(data_dir) -> World:
    d = Path(data_dir)
    cfg = json.loads((d / "config.json").read_text())
    lon0, lat1, dlon, dlat, h, w = _geometry(cfg)
    sea_below = float(cfg.get("sea_below_m", 0.0))
    runup = float(cfg.get("max_runup_m", 10.0))

    elev = sample_dem(d / "dem.asc", lon0, lat1, dlon, dlat, h, w)
    sea = np.isnan(elev) | (elev <= sea_below)
    flood = ~sea & (elev <= runup)

    road = rasterize_roads(json.loads((d / "roads.geojson").read_text()), lon0, lat1, dlon, dlat, h, w)
    road &= ~sea
    if not road.any():
        raise ValueError("Tidak ada jalan di dalam bbox/daratan; periksa roads.geojson dan config.bbox")
    road_yx = np.argwhere(road)

    shelter = np.zeros((h, w), dtype=bool)
    with open(d / "shelters.csv", newline="") as f:
        for r in csv.DictReader(f):
            cx = int((float(r["lon"]) - lon0) / dlon)
            cy = int((lat1 - float(r["lat"])) / dlat)
            if not (0 <= cx < w and 0 <= cy < h):
                continue
            k = np.argmin((road_yx[:, 0] - cy) ** 2 + (road_yx[:, 1] - cx) ** 2)  # snap ke jalan
            sy, sx = road_yx[k]
            shelter[max(sy - 1, 0):sy + 2, max(sx - 1, 0):sx + 2] = True
    if cfg.get("high_ground_is_safe", True):
        shelter |= road & ~sea & (elev > runup)
    shelter &= ~sea
    if not shelter.any():
        raise ValueError("Tidak ada shelter/dataran tinggi di dalam area; periksa shelters.csv dan max_runup_m")

    walkable = (road | shelter) & ~sea
    blocked = ~walkable
    dist = bfs_from(shelter, walkable)

    wd = bfs_from(sea, sea | flood)
    wave_dist = np.where(wd == INF, INF, np.maximum(wd - 1, 0)).astype(np.int32)

    spawn = np.argwhere(road & flood & (dist < INF) & ~shelter)
    if len(spawn) == 0:
        raise ValueError("Tidak ada jalan rawan-genangan yang terhubung ke shelter")
    info = {"source": str(d), "grid": (h, w), "road_cells": int(road.sum()),
            "spawn_cells": int(len(spawn)), "shelter_cells": int(shelter.sum())}
    return World(blocked, shelter, dist, spawn, wave_dist, info)
