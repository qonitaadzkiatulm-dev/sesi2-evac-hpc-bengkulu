"""Model evakuasi berbasis agen di atas grid 2D.

Skema:
- Laut di sisi barat (x kecil), dataran tinggi/shelter di sisi timur (x besar).
- Sungai vertikal membelah kota dan hanya bisa dilewati lewat jembatan (bottleneck).
- Penduduk mulai bergerak setelah peringatan + waktu reaksi individu.
- Setelah tsunami tiba, muka gelombang merambat ke daratan; agen yang terlewati = korban.
DATA SINTETIS: ganti build_map() dengan DEM, jaringan jalan, dan lokasi shelter nyata.
"""
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

W, H = 120, 80          # ukuran grid (1 sel = 10 m)
SEA_COLS = 8            # kolom 0..7 adalah laut
RIVER_X = 60            # kolom sungai
SHELTER_COLS = 3        # lebar zona shelter di tepi timur
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1))
INF = np.iinfo(np.int32).max


@dataclass(eq=False)
class World:
    """Peta siap-simulasi (sintetis atau dari data nyata)."""
    blocked: np.ndarray    # bool HxW: tidak bisa dilewati (laut, non-jalan, penghalang)
    shelter: np.ndarray    # bool HxW: sel tujuan evakuasi
    dist: np.ndarray       # int32 HxW: jarak langkah ke tujuan terdekat
    spawn: np.ndarray      # Nx2 (y, x): kandidat lokasi awal penduduk
    wave_dist: np.ndarray  # int32 HxW: jarak sel dari laut; INF = tidak terjangkau gelombang
    info: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    n_agents: int = 1000
    warning_delay_min: float = 5.0     # jeda sirine/peringatan setelah gempa
    tsunami_arrival_min: float = 30.0  # waktu tiba gelombang di garis pantai
    n_shelters: int = 3
    n_bridges: int = 2
    cell_capacity: int = 6
    dt_s: float = 10.0
    wave_speed_cells: float = 0.5      # sel per langkah (~5 m/s)
    max_minutes: float = 90.0
    seed: int = 0
    data_dir: str = ""                 # kosong = peta sintetis; isi = folder data nyata


@lru_cache(maxsize=64)
def build_map(n_shelters: int, n_bridges: int):
    """Peta sintetis: kembalikan (blocked, shelter_mask, dist). Di-cache per proses."""
    blocked = np.zeros((H, W), dtype=bool)
    blocked[:, :SEA_COLS] = True
    rng = np.random.default_rng(42)  # seed tetap: peta sama antar skenario
    for _ in range(140):
        x = int(rng.integers(SEA_COLS + 2, W - SHELTER_COLS - 3))
        y = int(rng.integers(0, H - 2))
        if RIVER_X - 2 <= x <= RIVER_X + 1:
            continue
        blocked[y:y + 2, x:x + 2] = True
    blocked[:, RIVER_X] = True
    for y in np.linspace(8, H - 9, n_bridges).astype(int):
        blocked[y - 1:y + 2, RIVER_X - 1:RIVER_X + 2] = False
    shelter = np.zeros((H, W), dtype=bool)
    for y in np.linspace(10, H - 11, n_shelters).astype(int):
        shelter[y - 3:y + 4, W - SHELTER_COLS:] = True
    blocked[shelter] = False
    return blocked, shelter, _bfs(blocked, shelter)


def bfs_from(sources, passable):
    """BFS 4-arah dari sel `sources` melalui sel `passable`; INF jika tak terjangkau."""
    h, w = passable.shape
    dist = np.full((h, w), INF, dtype=np.int32)
    q = deque()
    for y, x in zip(*np.nonzero(sources)):
        dist[y, x] = 0
        q.append((y, x))
    while q:
        y, x = q.popleft()
        for dx, dy in MOVES:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and passable[ny, nx] and dist[ny, nx] > dist[y, x] + 1:
                dist[ny, nx] = dist[y, x] + 1
                q.append((ny, nx))
    return dist


def _bfs(blocked, shelter):
    return bfs_from(shelter, ~blocked)


@lru_cache(maxsize=64)
def synthetic_world(n_shelters: int, n_bridges: int) -> World:
    blocked, shelter, dist = build_map(n_shelters, n_bridges)
    cand = np.argwhere(~blocked[:, SEA_COLS:RIVER_X - 1])
    cand[:, 1] += SEA_COLS
    cols = np.maximum(np.arange(W) - SEA_COLS, 0).astype(np.int32)
    return World(blocked, shelter, dist, cand, np.tile(cols, (H, 1)), {"source": "synthetic"})


@lru_cache(maxsize=8)
def _cached_real_world(data_dir: str) -> World:
    from .data import load_world
    return load_world(data_dir)


def get_world(sc) -> World:
    if sc.data_dir:
        return _cached_real_world(sc.data_dir)
    return synthetic_world(sc.n_shelters, sc.n_bridges)


def run(sc: Scenario) -> dict:
    """Jalankan satu skenario; deterministik untuk seed yang sama."""
    world = get_world(sc)
    shelter, dist, wave_dist = world.shelter, world.dist, world.wave_dist
    h, w = world.blocked.shape
    rng = np.random.default_rng(sc.seed)

    pick = world.spawn[rng.integers(0, len(world.spawn), sc.n_agents)]
    ay, ax = pick[:, 0].copy(), pick[:, 1].copy()
    speed = rng.choice([0.5, 0.75, 1.0], size=sc.n_agents, p=[0.2, 0.3, 0.5])  # anak/lansia/dewasa
    react = rng.uniform(0, 3.0, sc.n_agents)                                   # menit
    start = np.ceil((sc.warning_delay_min + react) * 60 / sc.dt_s).astype(int)
    budget = np.zeros(sc.n_agents)
    status = np.zeros(sc.n_agents, dtype=np.int8)  # 0 bergerak, 1 selamat, 2 korban
    done_step = np.full(sc.n_agents, -1)
    occ = np.zeros((h, w), dtype=np.int16)
    np.add.at(occ, (ay, ax), 1)

    arrive = int(sc.tsunami_arrival_min * 60 / sc.dt_s)
    n_steps = int(sc.max_minutes * 60 / sc.dt_s)
    order = np.arange(sc.n_agents)
    unreachable = dist[ay, ax] == INF

    for t in range(n_steps):
        reach = (t - arrive) * sc.wave_speed_cells if t >= arrive else -1.0
        rng.shuffle(order)
        for i in order:
            if status[i] != 0:
                continue
            if wave_dist[ay[i], ax[i]] <= reach:
                status[i], done_step[i] = 2, t
                occ[ay[i], ax[i]] -= 1
                continue
            if t < start[i] or unreachable[i]:
                continue
            budget[i] += speed[i]
            while budget[i] >= 1.0:
                y, x = ay[i], ax[i]
                best, bd = None, dist[y, x]
                for dx, dy in MOVES:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and dist[ny, nx] < bd and occ[ny, nx] < sc.cell_capacity:
                        best, bd = (ny, nx), dist[ny, nx]
                if best is None:        # macet: tunggu
                    budget[i] = min(budget[i], 1.0)
                    break
                occ[y, x] -= 1
                occ[best] += 1
                ay[i], ax[i] = best
                budget[i] -= 1.0
                if shelter[best]:
                    status[i], done_step[i] = 1, t
                    occ[best] -= 1
                    break
        if not (status == 0).any():
            break

    safe = status == 1
    return {
        **{k: v for k, v in sc.__dict__.items() if k != "dt_s"},
        "survival_rate": float(safe.mean()),
        "casualties": int((~safe).sum()),
        "mean_evac_min": float(done_step[safe].mean() * sc.dt_s / 60) if safe.any() else float("nan"),
    }
