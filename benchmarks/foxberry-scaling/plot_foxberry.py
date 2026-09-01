#!/usr/bin/env python
"""Plot the foxberry-scaling results in the exact style of FoxBerry's
scaling_single_phase_packed_bed.py, overlaying the FoxBerry reference numbers so the two codes
are directly comparable: loglog, x = number of processors (MPI ranks x 1 thread), y = execution
time per step [s], plus the ideal-halving line anchored at each curve's first point.

peclet GPU results (foxberry_gpu.sh) are drawn as horizontal dashed levels labeled "N x H100" --
a GPU count has no honest position on a core-count axis.

Usage:  python plot_foxberry.py [--results results/snellius-genoa] [--gpu results/snellius-h100]
"""
import argparse
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import matplotlib.ticker as ticker       # noqa: E402
import numpy as np                       # noqa: E402

# FoxBerry reference (FoxBerry/scaling/scaling_single_phase_packed_bed.py, verbatim).
FB_PROCS = np.array([24, 48, 96, 192, 384, 768, 1536])
FB = {
    "single": np.array([3.27e2, 1.66e2, 8.43e1, 4.22e1, 2.11e1, 1.06e1, 5.08e0]),
    "packed": np.array([3.85e2, 1.84e2, 9.83e1, 4.8e1, 2.42e1, 1.2e1, 5.44e0]),
}
TITLE = {
    "single": "Scaling single phase flow 3D (64M cells)",
    "packed": "Scaling packed bed flow 3D (64M cells, 5000 particles)",
}

ap = argparse.ArgumentParser()
ap.add_argument("--results", default="results/snellius-genoa")
ap.add_argument("--gpu", default="results/snellius-h100")
ap.add_argument("--tag", default="", help="only JSONs with this tag suffix")
args = ap.parse_args()


def collect(resdir, prefix, key):
    """-> sorted [(n, seconds_per_step, json)] for fb_<case>_<prefix><n><tag>.json files."""
    rows = []
    for f in sorted(glob.glob(os.path.join(resdir, "fb_*.json"))):
        base = os.path.basename(f)[:-5]
        parts = base.split("_")
        if len(parts) < 3 or not parts[2].startswith(prefix):
            continue
        tag = "_".join(parts[3:])
        if tag != args.tag.lstrip("_"):
            continue
        d = json.load(open(f))
        rows.append((parts[1], int(parts[2][len(prefix):]), d["ms_per_step"] / 1e3, d))
    return [(n, t, d) for c, n, t, d in rows if c == key]


def ideal(x, y0):
    return y0 * x[0] / np.asarray(x, float)


for case in ("single", "packed"):
    fig, ax = plt.subplots()
    ax.loglog(FB_PROCS, FB[case], ls="--", linewidth=2.0, marker="o", label="FoxBerry")
    ax.loglog(FB_PROCS, ideal(FB_PROCS, FB[case][0]), ls="-", linewidth=1.0, color="g",
              label="ideal")
    cpu = collect(args.results, "np", case)
    if cpu:
        n = [r[0] for r in cpu]
        t = [r[1] for r in cpu]
        ax.loglog(n, t, ls="--", linewidth=2.0, marker="s", color="tab:red", label="peclet.flow")
        ax.loglog(n, ideal(n, t[0]), ls="-", linewidth=1.0, color="g")
    for ng, tg, _ in collect(args.gpu, "gpu", case):
        ax.axhline(tg, ls=":", linewidth=1.2, color="tab:purple")
        ax.annotate(f"{ng}x H100", (FB_PROCS[0], tg), fontsize=8, color="tab:purple",
                    va="bottom")
    ax.set_title(TITLE[case])
    ax.set_xlabel("Number of processors")
    ax.set_ylabel("Execution time per step [s]")
    ax.xaxis.minorticks_off()
    ax.xaxis.set_major_locator(ticker.FixedLocator(FB_PROCS))
    ax.xaxis.set_major_formatter(ticker.FixedFormatter([str(p) for p in FB_PROCS]))
    ax.legend()
    out = f"scaling_{case}.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"[plot] {out}")

    print(f"\n{TITLE[case]}")
    print(f"  {'procs':>6}  {'FoxBerry s/step':>15}  {'peclet s/step':>14}  {'speedup':>8}")
    cpu_map = {n: t for n, t, _ in cpu}
    for p, tf in zip(FB_PROCS, FB[case]):
        tp = cpu_map.get(p)
        print(f"  {p:>6}  {tf:>15.3g}  " +
              (f"{tp:>14.3g}  {tf / tp:>8.1f}x" if tp else f"{'-':>14}  {'-':>8}"))
    for n, t, _ in collect(args.gpu, "gpu", case):
        print(f"  {n:>4}xH100  {'-':>13}  {t:>14.3g}")
