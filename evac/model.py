"""Model evakuasi berbasis agen di atas grid 2D.

Skema:
- Laut di sisi barat (x kecil), dataran tinggi/shelter di sisi timur (x besar).
- Sungai vertikal membelah kota dan hanya bisa dilewati lewat jembatan (bottleneck).
- Penduduk mulai bergerak setelah peringatan + waktu reaksi individu.
- Setelah tsunami tiba, muka gelombang merambat ke daratan; agen yang terlewati = korban.
DATA SINTETIS: ganti build_map() dengan DEM, jaringan jalan, dan lokasi shelter nyata.
"""
from collections import deque
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

W, H = 120, 80          # ukuran grid (1 sel = 10 m)
SEA_COLS = 8            # kolom 0..7 adalah laut
RIVER_X = 60            # kolom sungai
SHELTER_COLS = 3        # lebar zona shelter di tepi timur
MOVES = ((1, 0), (-1, 0), (0, 1), (0, -1))
INF = np.iinfo(np.int32).max


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


@lru_cache(maxsize=64)
def build_map(n_shelters: int, n_bridges: int):
    """Kembalikan (blocked, shelter_mask, dist). Hasil di-cache per proses."""
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


def _bfs(blocked, shelter):
    dist = np.full((H, W), INF, dtype=np.int32)
    q = deque()
    for y, x in zip(*np.nonzero(shelter)):
        dist[y, x] = 0
        q.append((y, x))
    while q:
        y, x = q.popleft()
        for dx, dy in MOVES:
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and not blocked[ny, nx] and dist[ny, nx] > dist[y, x] + 1:
                dist[ny, nx] = dist[y, x] + 1
                q.append((ny, nx))
    return dist


def run(sc: Scenario) -> dict:
    """Jalankan satu skenario; deterministik untuk seed yang sama."""
    blocked, shelter, dist = build_map(sc.n_shelters, sc.n_bridges)
    rng = np.random.default_rng(sc.seed)

    cand = np.argwhere(~blocked[:, SEA_COLS:RIVER_X - 1])
    pick = cand[rng.integers(0, len(cand), sc.n_agents)]
    ay, ax = pick[:, 0].copy(), pick[:, 1].copy() + SEA_COLS
    speed = rng.choice([0.5, 0.75, 1.0], size=sc.n_agents, p=[0.2, 0.3, 0.5])  # anak/lansia/dewasa
    react = rng.uniform(0, 3.0, sc.n_agents)                                   # menit
    start = np.ceil((sc.warning_delay_min + react) * 60 / sc.dt_s).astype(int)
    budget = np.zeros(sc.n_agents)
    status = np.zeros(sc.n_agents, dtype=np.int8)  # 0 bergerak, 1 selamat, 2 korban
    done_step = np.full(sc.n_agents, -1)
    occ = np.zeros((H, W), dtype=np.int16)
    np.add.at(occ, (ay, ax), 1)

    arrive = int(sc.tsunami_arrival_min * 60 / sc.dt_s)
    n_steps = int(sc.max_minutes * 60 / sc.dt_s)
    order = np.arange(sc.n_agents)
    unreachable = dist[ay, ax] == INF

    for t in range(n_steps):
        front = -1.0 if t < arrive else SEA_COLS + (t - arrive) * sc.wave_speed_cells
        rng.shuffle(order)
        for i in order:
            if status[i] != 0:
                continue
            if ax[i] <= front:
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
                    if 0 <= ny < H and 0 <= nx < W and dist[ny, nx] < bd and occ[ny, nx] < sc.cell_capacity:
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
