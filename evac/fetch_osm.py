"""Unduh jaringan jalan OpenStreetMap (Overpass API) -> roads.geojson.

  python -m evac.fetch_osm --data-dir data/bengkulu
Membaca bbox dari <data-dir>/config.json. Butuh internet; data (c) kontributor OpenStreetMap (ODbL).
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

HIGHWAYS = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street|track|path|footway"
URL = "https://overpass-api.de/api/interpreter"


def build_query(bbox):
    lon0, lat0, lon1, lat1 = bbox
    return (f'[out:json][timeout:90];way["highway"~"^({HIGHWAYS})$"]'
            f'({lat0},{lon0},{lat1},{lon1});out geom;')


def overpass_to_geojson(resp):
    feats = []
    for el in resp.get("elements", []):
        if el.get("type") == "way" and len(el.get("geometry", [])) >= 2:
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            feats.append({"type": "Feature", "properties": {"id": el["id"], **el.get("tags", {})},
                          "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    a = ap.parse_args()
    d = Path(a.data_dir)
    cfg = json.loads((d / "config.json").read_text())
    body = urllib.parse.urlencode({"data": build_query(cfg["bbox"])}).encode()
    req = urllib.request.Request(URL, data=body, headers={"User-Agent": "evac-hpc-student-project"})
    with urllib.request.urlopen(req, timeout=120) as r:
        gj = overpass_to_geojson(json.load(r))
    (d / "roads.geojson").write_text(json.dumps(gj))
    print(f"{len(gj['features'])} ruas jalan -> {d / 'roads.geojson'}")


if __name__ == "__main__":
    main()
