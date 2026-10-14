"""Ukur speedup & efisiensi paralel (strong scaling) pada sweep yang sama."""
import argparse
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .sweep import make_scenarios, run_mp, run_serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args()
    scs = make_scenarios(a.reps)
    rows = []
    for w in a.workers:
        t0 = time.perf_counter()
        run_serial(scs) if w == 1 else run_mp(scs, w)
        rows.append({"workers": w, "seconds": time.perf_counter() - t0})
    df = pd.DataFrame(rows)
    df["speedup"] = df.seconds.iloc[0] / df.seconds
    df["efficiency"] = df.speedup / df.workers
    df.to_csv("results/benchmark.csv", index=False)
    print(df.round(2).to_string(index=False))
    plt.plot(df.workers, df.speedup, "o-", label="terukur")
    plt.plot(df.workers, df.workers, "k--", label="ideal")
    plt.xlabel("Jumlah worker"); plt.ylabel("Speedup"); plt.legend()
    plt.savefig("results/speedup.png", dpi=130)


if __name__ == "__main__":
    main()
