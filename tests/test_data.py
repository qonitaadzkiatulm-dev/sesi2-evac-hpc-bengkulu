import json

import numpy as np

from evac.data import load_world, rasterize_roads
from evac.demo import make_demo
from evac.fetch_osm import build_query, overpass_to_geojson
from evac.model import INF, Scenario, run


def test_load_demo_world(tmp_path):
    w = load_world(make_demo(tmp_path))
    h, wd = w.blocked.shape
    assert w.shelter.any() and len(w.spawn) > 0
    ys, xs = w.spawn[:, 0], w.spawn[:, 1]
    assert not w.blocked[ys, xs].any()          # penduduk hanya di jalan
    assert (w.dist[ys, xs] < INF).all()         # semua terhubung ke shelter
    assert (w.wave_dist[ys, xs] < INF).all()    # semua di zona rawan genangan


def test_run_with_data_dir(tmp_path):
    d = str(make_demo(tmp_path))
    r = run(Scenario(n_agents=200, data_dir=d, seed=1))
    assert 0.0 <= r["survival_rate"] <= 1.0
    early = run(Scenario(n_agents=200, data_dir=d, warning_delay_min=0, tsunami_arrival_min=20, seed=2))
    late = run(Scenario(n_agents=200, data_dir=d, warning_delay_min=20, tsunami_arrival_min=20, seed=2))
    assert early["survival_rate"] >= late["survival_rate"]


def test_rasterize_diagonal_is_4_connected():
    gj = {"features": [{"geometry": {"type": "LineString", "coordinates": [[0.0, 10.0], [10.0, 0.0]]}}]}
    r = rasterize_roads(gj, 0.0, 10.0, 1.0, 1.0, 10, 10)
    assert r.sum() >= 10
    ys, xs = np.nonzero(r)
    # setiap sel punya tetangga 4-arah (tidak ada sel terputus secara diagonal)
    for y, x in zip(ys, xs):
        nb = sum(0 <= y + dy < 10 and 0 <= x + dx < 10 and r[y + dy, x + dx]
                 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        assert nb >= 1


def test_overpass_converter():
    resp = {"elements": [{"type": "way", "id": 1, "tags": {"highway": "residential"},
                          "geometry": [{"lat": -3.8, "lon": 102.2}, {"lat": -3.81, "lon": 102.21}]},
                         {"type": "node", "id": 2}]}
    gj = overpass_to_geojson(resp)
    assert len(gj["features"]) == 1
    assert gj["features"][0]["geometry"]["coordinates"][0] == [102.2, -3.8]
    assert "out geom" in build_query([102.2, -3.9, 102.3, -3.8])
