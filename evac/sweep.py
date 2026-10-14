"""Parameter sweep (Monte Carlo) dengan 3 backend: serial, multiprocessing, mpi.

Setiap skenario independen -> "embarrassingly parallel", cocok untuk HPC.
Contoh:
  python -m evac.sweep --backend multiprocessing --workers 4 --reps 5
  mpirun -n 64 python -m evac.sweep --backend mpi --reps 20
"""
import argparse
import itertools
import time
from multiprocessing import Pool

import pandas as pd

from .model import Scenario, run


def make_scenarios(reps, n_agents=1000):
    grid = itertools.product([0, 5, 10, 15], [2, 4, 6], [1, 2, 3], range(reps))
    return [Scenario(n_agents=n_agents, warning_delay_min=d, n_shelters=s, n_bridges=b, seed=r)
            for d, s, b, r in grid]


def run_serial(scs):
    return [run(s) for s in scs]


def run_mp(scs, workers):
    with Pool(workers) as p:
        return p.map(run, scs, chunksize=1)


def run_mpi(scs):
    from mpi4py import MPI
    comm = MPI.COMM_WORLD
    mine = [run(s) for s in scs[comm.Get_rank()::comm.Get_size()]]  # bagi rata per rank
    parts = comm.gather(mine, root=0)
    return [r for p in parts for r in p] if comm.Get_rank() == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["serial", "multiprocessing", "mpi"], default="serial")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--agents", type=int, default=1000)
    ap.add_argument("--out", default="results/results.csv")
    a = ap.parse_args()

    scs = make_scenarios(a.reps, a.agents)
    t0 = time.perf_counter()
    res = {"serial": lambda: run_serial(scs),
           "multiprocessing": lambda: run_mp(scs, a.workers),
           "mpi": lambda: run_mpi(scs)}[a.backend]()
    dt = time.perf_counter() - t0
    if res is not None:
        pd.DataFrame(res).to_csv(a.out, index=False)
        print(f"{len(scs)} skenario | backend={a.backend} | {dt:.1f} s -> {a.out}")


if __name__ == "__main__":
    main()
