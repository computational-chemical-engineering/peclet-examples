#!/usr/bin/env python
"""Plot the foxberry-scaling results in the style of FoxBerry's
scaling_single_phase_packed_bed.py, overlaying the FoxBerry reference numbers so the two codes are
directly comparable: loglog, x = number of processors (MPI ranks x 1 thread), y = execution time
per step [s], plus the ideal-halving line anchored at each curve's first point.

Series are selected from the JSON CONTENTS (case / bcmode / grid / backend), not from filenames,
so renaming a result never silently drops or mislabels a curve.

peclet GPU results are drawn as horizontal dashed levels labeled "N x H100" -- a GPU count has no
honest position on a core-count axis.

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
    "single": "Scaling single phase flow 3D (~64M cells)",
    "packed": "Scaling packed bed flow 3D (~64M cells, 5000 particles)",
}

ap = argparse.ArgumentParser()
ap.add_argument("--results", default="results/snellius-genoa")
ap.add_argument("--gpu", default="results/snellius-h100")
args = ap.parse_args()


def load(resdir):
    out = []
    for f in sorted(glob.glob(os.path.join(resdir, "fb_*.json"))):
        try:
            out.append(json.load(open(f)))
        except Exception as e:
            print(f"  (skipping unreadable {os.path.basename(f)}: {e})")
    return out


def capped(d):
    """A run in which ANY step hit the pressure iteration cap is INVALID, not slow: that step's
    time is set by PMAXIT rather than by convergence. Judge on the MAX, not the mean — a run where
    only some steps cap has a mean below PMAXIT and looks converged (measured: np=1536 packed
    averaged 122 with individual steps at 200). Older JSONs carry only the mean; fall back to it."""
    mx = d.get("pressure_iters_max")
    if mx is None:
        return d["pressure_iters_per_step"] >= d["pmaxit"] - 0.5
    return mx >= d["pmaxit"]


def pick(rows, case, bcmode, gn, gpu=False, telescope=0):
    """Sorted [(np, seconds_per_step)] for one series, from the JSON fields."""
    sel, drop = [], []
    for d in rows:
        if (d.get("case") != case or d.get("bcmode", "foxberry") != bcmode
                or d["global"][0] != gn or (d.get("backend") == "Cuda") != gpu
                or int(d.get("telescope", 0)) != telescope):
            continue
        (drop if capped(d) else sel).append((d["np"], d["ms_per_step"] / 1e3))
    for n, t in sorted(set(drop)):
        print(f"  (dropped np={n}: capped at {int(rows[0]['pmaxit'])} pressure iters — invalid)")
    return sorted(set(sel))


def ideal(x, y0):
    return y0 * x[0] / np.asarray(x, float)


cpu_rows, gpu_rows = load(args.results), load(args.gpu)

# (case, bcmode, grid, telescope, label, colour, marker) -- the peclet series drawn on each figure.
SERIES = {
    "single": [
        ("single", "foxberry", 384, 1, "peclet.flow 384³, telescoped MG", "tab:red", "s"),
        ("single", "foxberry", 384, 0, "peclet.flow 384³, in-place MG", "tab:pink", "s"),
        ("single", "foxberry", 400, 0, "peclet.flow 400³, in-place MG", "tab:orange", "^"),
    ],
    "packed": [
        ("packed", "foxberry", 384, 1, "peclet.flow 384³, FoxBerry BCs, telescoped MG", "tab:red", "s"),
        ("packed", "foxberry", 384, 0, "peclet.flow 384³, FoxBerry BCs, in-place MG", "tab:pink", "s"),
        ("packed", "periodic", 384, 0, "peclet.flow 384³, periodic BCs, in-place MG", "tab:gray", "o"),
    ],
}

for case in ("single", "packed"):
    fig, ax = plt.subplots()
    ax.loglog(FB_PROCS, FB[case], ls="--", lw=2.0, marker="o", color="tab:blue",
              label="FoxBerry 401³ (64.5M)")
    ax.loglog(FB_PROCS, ideal(FB_PROCS, FB[case][0]), ls="-", lw=1.0, color="g", label="ideal")

    print(f"\n{TITLE[case]}")
    header = f"  {'procs':>6}  {'FoxBerry':>10}"
    drawn = []
    for c, bc, gn, tel, lab, col, mk in SERIES[case]:
        pts = pick(cpu_rows, c, bc, gn, telescope=tel)
        if not pts:
            continue
        n = [p[0] for p in pts]
        t = [p[1] for p in pts]
        ax.loglog(n, t, ls="--" if tel else ":", lw=2.0 if tel else 1.4, marker=mk, color=col,
                  label=lab, mfc=col if tel else "none")
        if tel:
            ax.loglog(n, ideal(n, t[0]), ls="-", lw=0.8, color=col, alpha=0.4)
        drawn.append((lab, dict(pts)))
        header += f"  {lab.replace('peclet.flow ', ''):>30}"
    for c, bc, gn, tel, lab, col, mk in SERIES[case]:
        for ng, tg in pick(gpu_rows, c, bc, gn, gpu=True, telescope=tel):
            ax.axhline(tg, ls=":", lw=1.2, color="tab:purple")
            ax.annotate(f"{ng}x H100 ({gn}³)", (FB_PROCS[0], tg), fontsize=8,
                        color="tab:purple", va="bottom")

    ax.set_title(TITLE[case])
    ax.set_xlabel("Number of processors")
    ax.set_ylabel("Execution time per step [s]")
    ax.xaxis.minorticks_off()
    ax.xaxis.set_major_locator(ticker.FixedLocator(FB_PROCS))
    ax.xaxis.set_major_formatter(ticker.FixedFormatter([str(p) for p in FB_PROCS]))
    ax.legend(fontsize=8)
    if case == "packed" and any("periodic BCs" in d[0] for d in drawn):
        ax.text(0.02, 0.02,
                "gray: periodic BCs + triply-periodic bed (same size, not FoxBerry's BCs)",
                transform=ax.transAxes, fontsize=7, va="bottom", color="dimgray")
    out = f"scaling_{case}.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"[plot] {out}")

    if not drawn:
        print("  (no peclet results yet)")
        continue
    print(header + f"  {'speedup vs FB':>14}")
    for p, tf in zip(FB_PROCS, FB[case]):
        row = f"  {p:>6}  {tf:>10.3g}"
        best = None
        for lab, m in drawn:
            v = m.get(p)
            row += f"  {(f'{v:.3g}' if v else '-'):>30}"
            if v and (best is None or v < best):
                best = v
        print(row + f"  {(f'{tf / best:.1f}x' if best else '-'):>14}")

# ---- diagnosis figure: where the strong-scaling deficit actually comes from ------------------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
for case, bc, gn, tel, lab, col, mk in [
        ("single", "foxberry", 384, 1, "single-phase, telescoped", "tab:red", "s"),
        ("single", "foxberry", 384, 0, "single-phase, in-place", "tab:pink", "s"),
        ("packed", "foxberry", 384, 1, "packed bed (FoxBerry BCs), telescoped", "tab:green", "o"),
        ("packed", "foxberry", 384, 0, "packed bed (FoxBerry BCs), in-place", "tab:olive", "o"),
        ("packed", "periodic", 384, 0, "packed bed (periodic), in-place", "tab:gray", "o")]:
    rows = [d for d in cpu_rows
            if d.get("case") == case and d.get("bcmode", "foxberry") == bc
            and d["global"][0] == gn and int(d.get("telescope", 0)) == tel and not capped(d)]
    if not rows:
        continue
    pts = sorted({(d["np"], d["pressure_iters_per_step"], d["ms_per_step"]) for d in rows})
    n = [p[0] for p in pts]
    ls = "--" if tel else ":"
    a1.loglog(n, [p[1] for p in pts], ls=ls, lw=2, marker=mk, color=col, label=lab)
    a2.loglog(n, [p[2] / p[1] for p in pts], ls=ls, lw=2, marker=mk, color=col, label=lab)
a1.set_title("Pressure iterations per step")
a1.set_ylabel("iterations")
a2.set_title("Time per pressure iteration")
a2.set_ylabel("ms / iteration")
# ideal on the right panel = perfect strong scaling of the per-iteration work. Drawn BEFORE the
# axis formatting, or its autoscale resets the fixed rank ticks.
ns = np.array([24, 1536], float)
a2.loglog(ns, 2200.6 * ns[0] / ns, ls="-", lw=1, color="g")
a2.annotate("ideal", (1536, 2200.6 * 24 / 1536), fontsize=8, color="g", va="top", ha="right")
for ax in (a1, a2):
    ax.set_xlabel("Number of processors")
    ax.set_xscale("log")
    ax.xaxis.minorticks_off()
    ax.xaxis.set_major_locator(ticker.FixedLocator(FB_PROCS))
    ax.xaxis.set_major_formatter(ticker.FixedFormatter([str(p) for p in FB_PROCS]))
    ax.set_xlim(20, 1900)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, which="major")
fig.suptitle("Where the strong-scaling deficit comes from: iterations grow (left), while the work "
             "per iteration scales better than ideal (right)", fontsize=10)
fig.tight_layout()
fig.savefig("scaling_diagnosis.png", dpi=160, bbox_inches="tight")
print("[plot] scaling_diagnosis.png")
