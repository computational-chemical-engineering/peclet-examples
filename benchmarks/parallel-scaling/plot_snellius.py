#!/usr/bin/env python
"""Cross-node (Snellius Genoa) figures for the parallel-scaling study.

Reads results/snellius-genoa/*.json and writes snellius_weak.png:
weak-scaling efficiency + aggregate throughput vs nodes, peclet (all draws shown,
median line) vs CaNS vs incflo (vs OpenFOAM when its data lands).
"""
import collections
import glob
import json
import os
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results", "snellius-genoa")

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "font.size": 10,
    "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
})

CELLS_PER_NODE = 188.7  # Mcells (768x640x384 per node)

# peclet: all bound/unbound draws per node count; plot the median, mark the draws
draws = collections.defaultdict(list)
for f in glob.glob(os.path.join(RES, "weak_n*_r96_t2*.json")):
    d = json.load(open(f))
    draws[d["np"] // 96].append(d["ms_per_step"])
pn = sorted(draws)
pmed = [statistics.median(draws[n]) for n in pn]

refs = {}
for code in ("cans", "incflo", "of"):
    pts = []
    for f in sorted(glob.glob(os.path.join(RES, f"{code}_weak_n*.json")),
                    key=lambda p: int(p.split("_n")[-1].split(".")[0])):
        d = json.load(open(f))
        pts.append((d["np"] // 192, d["ms_per_step"], d["mcells_per_s"]))
    if pts:
        refs[code] = pts

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

# efficiency panel
ax1.plot(pn, [100 * pmed[0] / m for m in pmed], "o-", color=BLUE, lw=2, ms=5,
         label="peclet.flow (median of 3)")
for n in pn:  # individual draws as small open markers: the honest spread
    ax1.plot([n] * len(draws[n]), [100 * pmed[0] / m for m in draws[n]], "o",
             ms=3.5, mfc="none", mec=BLUE, mew=1)
labels = {"cans": ("CaNS", ORANGE), "incflo": ("incflo", YELLOW), "of": ("OpenFOAM", AQUA)}
for code, pts in refs.items():
    lbl, col = labels[code]
    ns = [p[0] for p in pts]
    ax1.plot(ns, [100 * pts[0][1] / p[1] for p in pts], "s-", color=col, lw=2, ms=5, label=lbl)
ax1.axhline(100, ls="--", c=INK2, lw=0.8)
ax1.set_xscale("log", base=2)
ax1.set_xticks(pn, [str(n) for n in pn])
ax1.set_xlabel("Genoa nodes (188.7 Mcells/node fixed)")
ax1.set_ylabel("weak-scaling efficiency [%]")
ax1.set_ylim(0, 112)
ax1.set_title("Cross-node weak scaling", fontsize=10)
ax1.legend(fontsize=8, frameon=False, loc="center left")

# throughput panel
ax2.plot(pn, [CELLS_PER_NODE * n / (m / 1e3) for n, m in zip(pn, pmed)], "o-",
         color=BLUE, lw=2, ms=5, label="peclet.flow")
for code, pts in refs.items():
    lbl, col = labels[code]
    ax2.plot([p[0] for p in pts], [p[2] for p in pts], "s-", color=col, lw=2, ms=5, label=lbl)
ideal = [CELLS_PER_NODE * pmed[0] and CELLS_PER_NODE * n / (pmed[0] / 1e3) for n in pn]
ax2.plot(pn, ideal, ":", c=INK2, lw=1, label="ideal (peclet slope)")
ax2.set_xscale("log", base=2)
ax2.set_yscale("log")
ax2.set_xticks(pn, [str(n) for n in pn])
ax2.set_xlabel("Genoa nodes")
ax2.set_ylabel("aggregate Mcell/s")
ax2.set_title("Absolute throughput (log-log)", fontsize=10)
ax2.legend(fontsize=8, frameon=False, loc="upper left")

fig.tight_layout()
fig.savefig(os.path.join(HERE, "snellius_weak.png"), dpi=150)
print("snellius_weak.png")
