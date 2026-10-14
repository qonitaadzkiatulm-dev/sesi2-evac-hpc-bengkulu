"""Ringkas hasil sweep dan buat grafik."""
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="results/results.csv")
    ap.add_argument("--fig", default="results/survival.png")
    a = ap.parse_args()
    df = pd.read_csv(a.csv)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for s, g in df.groupby("n_shelters"):
        m = g.groupby("warning_delay_min")["survival_rate"].mean() * 100
        axes[0].plot(m.index, m.values, marker="o", label=f"{s} shelter")
    axes[0].set(xlabel="Jeda peringatan (menit)", ylabel="Tingkat selamat (%)", title="Efek peringatan & jumlah shelter")
    axes[0].legend()
    for b, g in df.groupby("n_bridges"):
        m = g.groupby("warning_delay_min")["survival_rate"].mean() * 100
        axes[1].plot(m.index, m.values, marker="s", label=f"{b} jembatan")
    axes[1].set(xlabel="Jeda peringatan (menit)", title="Efek jumlah jembatan (bottleneck)")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(a.fig, dpi=130)

    for col, name in (("n_shelters", "shelter"), ("n_bridges", "jembatan")):
        tbl = df.pivot_table(index="warning_delay_min", columns=col, values="survival_rate", aggfunc="mean") * 100
        print(f"\nTingkat selamat (%) per jeda peringatan (baris) x jumlah {name} (kolom)")
        print(tbl.round(1).to_string())


if __name__ == "__main__":
    main()
