"""Buat DATA DEMO (bukan data nyata) dengan format yang sama seperti data sungguhan.

Koordinat kira-kira di sekitar Pantai Panjang, Kota Bengkulu. DEM berupa lereng sintetis,
jalan berupa grid dengan sungai + 2 jembatan, dan 2 shelter. Gunanya menguji pipeline
sebelum Anda mengganti berkas dengan data asli (DEMNAS/SRTM, OSM, BPBD).
  python -m evac.demo --out data/demo_bengkulu
"""
import argparse
import json
from pathlib import Path

import numpy as np

BBOX = [102.250, -3.815, 102.265, -3.803]
COAST_LON = 102.2520
SLOPE = 0.0083       # naik ~0,83 m per 100 m ke arah timur
RIVER = (102.2580, 102.2584)


def make_demo(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lon0, lat0, lon1, lat1 = BBOX
    cs, m = 0.0001, 0.002
    xll, yll = lon0 - m, lat0 - m
    ncols = int(round((lon1 - lon0 + 2 * m) / cs))
    nrows = int(round((lat1 - lat0 + 2 * m) / cs))
    lons = xll + (np.arange(ncols) + 0.5) * cs
    lats = yll + nrows * cs - (np.arange(nrows) + 0.5) * cs
    mpd = 111320 * np.cos(np.radians(-3.81))
    elev = (lons[None, :] - COAST_LON) * mpd * SLOPE + 0.3 * np.sin(lats[:, None] * 800)
    with open(out / "dem.asc", "w") as f:
        f.write(f"ncols {ncols}\nnrows {nrows}\nxllcorner {xll}\nyllcorner {yll}\n"
                f"cellsize {cs}\nNODATA_value -9999\n")
        np.savetxt(f, elev, fmt="%.2f")

    feats = []

    def line(coords):
        feats.append({"type": "Feature", "properties": {},
                      "geometry": {"type": "LineString", "coordinates": coords}})

    ew = np.linspace(lat0 + 0.0015, lat1 - 0.0015, 6)
    for i, la in enumerate(ew):
        if i in (1, 4):                         # jembatan: jalan menyeberangi sungai
            line([[lon0, la], [lon1, la]])
        else:                                   # jalan terputus oleh sungai
            line([[lon0, la], [RIVER[0], la]])
            line([[RIVER[1], la], [lon1, la]])
    for lo in (102.2530, 102.2550, 102.2570, 102.2590, 102.2610, 102.2630):
        line([[lo, lat0], [lo, lat1]])
    (out / "roads.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    (out / "shelters.csv").write_text("name,lat,lon\nTES-A,-3.8060,102.2640\nTES-B,-3.8120,102.2640\n")
    (out / "config.json").write_text(json.dumps({
        "bbox": BBOX, "cell_m": 10, "sea_below_m": 0.0, "max_runup_m": 10.0,
        "high_ground_is_safe": True}, indent=2))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo_bengkulu")
    print("Data demo ditulis ke", make_demo(ap.parse_args().out))
