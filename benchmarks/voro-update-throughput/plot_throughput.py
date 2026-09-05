#!/usr/bin/env python
"""Figures for the Voronoi update-throughput benchmark.

Reads results/workstation/*.csv (bench_report --repair sweeps, one CSV per backend and
certificate) and results/snellius-h100/voro-mpi-26366044.out (bench_repair_mpi weak scaling),
writes workstation.png and snellius_h100.png next to this script.
"""
import csv
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

# The gallery's chart palette (validated: CVD dE 9.2 worst adjacent pair; aqua needs labels).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "font.size": 10,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
})
DISP = [1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2]  # the sweep, in units of the mean spacing


def read_sweep(name):
    rows = []
    with open(os.path.join(RES, "workstation", name)) as f:
        for r in csv.DictReader(l for l in f if not l.startswith("#")):
            rows.append({k: float(v) for k, v in r.items()})
    return rows


def workstation():
    series = [  # (file, colour, linestyle, label)
        ("repair_host_nearmiss.csv", BLUE, "-", "host, 8 threads · near-miss certificate"),
        ("repair_host_local_cert.csv", BLUE, "--", "host, 8 threads · local certificate"),
        ("repair_rtx5080_nearmiss.csv", ORANGE, "-", "RTX 5080 · near-miss certificate"),
        ("repair_rtx5080_local_cert.csv", ORANGE, "--", "RTX 5080 · local certificate"),
    ]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for fname, col, ls, lab in series:
        rows = [r for r in read_sweep(fname) if r["disp"] <= 0.0101]
        x = [r["disp"] for r in rows]
        ax1.plot(x, [r["speedup"] for r in rows], ls, color=col, lw=2, ms=6,
                 marker="o" if ls == "-" else "s", mfc=SURFACE, mew=1.6, label=lab)
        ax2.plot(x, [max(r["max_rel_v"], 1e-16) for r in rows], ls, color=col, lw=2, ms=6,
                 marker="o" if ls == "-" else "s", mfc=SURFACE, mew=1.6, label=lab)
    for ax in (ax1, ax2):
        ax.set_xscale("log")
        ax.set_xlabel("displacement per step  (units of the mean spacing)")
        ax.axvspan(7e-3, 0.0125, color=GRID, alpha=0.6, lw=0)
        ax.text(8.4e-3, 2.6 if ax is ax1 else 1e-15, "gate →\nrebuild", fontsize=8.5,
                color=INK2, ha="center", va="bottom")
    ax1.axhline(1.0, color=INK2, lw=1, ls=":")
    ax1.text(1.05e-4, 1.06, "= one cold build", fontsize=8.5, color=INK2)
    ax1.set_ylabel("repair speed-up over the cold build  (×)")
    ax1.set_title("Per-step update vs. rebuilding (N = 200 000)", loc="left", fontsize=11)
    ax1.set_ylim(0, 13.5)
    ax1.legend(loc="upper right", fontsize=8.5)
    ax2.set_yscale("log")
    ax2.set_ylabel("max relative cell-volume error per step")
    ax2.set_title("Exactness of the repair", loc="left", fontsize=11)
    ax2.set_ylim(3e-17, 3e-2)
    ax2.annotate("local certificate misses ~250\ngained neighbours per step", xy=(2e-3, 1.5e-4),
                 xytext=(2.5e-4, 3e-3), fontsize=8.5, color=INK2,
                 arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax2.annotate("near-miss certificate: exact to 1e-11", xy=(5e-4, 1.5e-11),
                 xytext=(1.2e-4, 3e-9), fontsize=8.5, color=INK2,
                 arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "workstation.png"), dpi=160)


def read_snellius():
    """{(np, sdf): [(disp, cold_ms, repair_ms, speedup, maxRelV), ...]}"""
    out = {}
    key = None
    pat = re.compile(r"^\s*0\.\d{3}\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.e+-]+)\s*$")
    with open(os.path.join(RES, "snellius-h100", "voro-mpi-26366044.out")) as f:
        for line in f:
            m = re.match(r"^---- np=(\d+): \S+bench_repair_mpi \d+ \d+( --sdf)?", line)
            if m:
                key = (int(m.group(1)), bool(m.group(2)))
                out[key] = []
                continue
            if line.startswith("---- np=") and "test_flow_mpi" in line:
                key = None
            m = pat.match(line)
            if m and key is not None:
                i = len(out[key])
                out[key].append((DISP[i], float(m.group(1)), float(m.group(2)),
                                 float(m.group(3)), float(m.group(4))))
    return out


def snellius():
    d = read_snellius()
    nps = [1, 2, 4]
    med = lambda xs: sorted(xs)[len(xs) // 2]
    cold = [med([r[1] for r in d[(n, False)]]) for n in nps]  # sweep median (row 1 carries warm-up)
    rep = [d[(n, False)][0][2] for n in nps]           # repair at 1e-4
    sdf = [d[(n, True)][0][2] for n in nps]            # SDF-scene repair at 1e-4
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for ys, col, lab in ((cold, BLUE, "cold build (distributed)"),
                         (sdf, AQUA, "repair, SDF scene"),
                         (rep, ORANGE, "repair, 1e-4 spacing/step")):
        ax1.plot(nps, ys, "o-", color=col, lw=2, ms=7, mfc=SURFACE, mew=1.6, label=lab)
        ax1.annotate(f"{ys[-1]:.0f} ms", (nps[-1], ys[-1]), xytext=(6, 0),
                     textcoords="offset points", va="center", fontsize=9, color=INK)
        ax2.plot(nps, [100 * ys[0] / y for y in ys], "o-", color=col, lw=2, ms=7,
                 mfc=SURFACE, mew=1.6, label=lab)
        ax2.annotate(f"{100 * ys[0] / ys[-1]:.0f} %", (nps[-1], 100 * ys[0] / ys[-1]),
                     xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
    ax1.set_ylabel("wall time per step  (ms)")
    ax1.set_ylim(0, 240)
    ax1.set_title("Weak scaling on H100s — 400 000 seeds per GPU", loc="left", fontsize=11)
    ax1.legend(loc="center right", fontsize=8.5, bbox_to_anchor=(1.0, 0.52))
    ax1.text(1.0, 62, "repair 4.0× → 4.6× faster\nthan rebuilding", fontsize=8.5, color=INK2)
    ax2.axhline(100, color=INK2, lw=1, ls=":")
    ax2.set_ylabel("weak-scaling efficiency  t(1 GPU) / t(n GPUs)  (%)")
    ax2.set_ylim(0, 110)
    ax2.set_title("Efficiency relative to one GPU", loc="left", fontsize=11)
    for ax in (ax1, ax2):
        ax.set_xticks(nps)
        ax.set_xlim(0.7, 4.8)
        ax.set_xlabel("GPUs (MPI ranks, one node)")
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "snellius_h100.png"), dpi=160)
    return d


if __name__ == "__main__":
    workstation()
    d = snellius()
    for k in sorted(d):
        print(k, [(r[0], r[1], r[2], r[3]) for r in d[k]][:2], "...")
