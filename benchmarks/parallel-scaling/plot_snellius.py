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

# ---- GPU: 1-32 H100 weak scaling + the pressure-solver ablation --------------------------------
G = os.path.join(HERE, "results", "snellius-h100")
gn = [1, 2, 4, 8, 16, 32]
gd = {n: json.load(open(os.path.join(G, f"weak_np{n}.json"))) for n in gn}
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
eff = [100 * gd[1]["ms_per_step"] / gd[n]["ms_per_step"] for n in gn]
ax1.plot(gn, eff, "o-", color=BLUE, lw=2, ms=5)
for n, e in zip(gn, eff):
    ax1.annotate(f"{e:.0f}%", (n, e), textcoords="offset points", xytext=(0, -14),
                 ha="center", fontsize=8, color=INK2)
ax1.axhline(100, ls="--", c=INK2, lw=0.8)
ax1.set_xscale("log", base=2)
ax1.set_xticks(gn, [str(n) for n in gn])
ax1.set_xlabel("H100 GPUs (47.2 Mcells/GPU fixed; 4 GPUs/node)")
ax1.set_ylabel("weak-scaling efficiency [%]")
ax1.set_ylim(0, 112)
ax1.set_title("GPU weak scaling — 3.5 Gcell/s on 32 H100", fontsize=10)

variants = [("", "MG-PCG + fine scope (default)", BLUE), ("_meanall", "mean removal: all levels", AQUA),
            ("_hoststage", "host-staged halo", YELLOW), ("_cheb", "Chebyshev", ORANGE),
            ("_amg", "GraphAMG bottom", "#e87ba4")]
x = range(len(variants))
w = 0.38
for off, N, hatch in ((-w / 2, 8, None), (w / 2, 16, "//")):
    vals = [json.load(open(os.path.join(G, f"weak_np{N}{v}.json")))["ms_per_step"]
            for v, _, _ in variants]
    ax2.bar([i + off for i in x], vals, w, color=[c for _, _, c in variants],
            edgecolor=SURFACE, linewidth=2, hatch=hatch)
ax2.plot([], [], "s", color=INK2, label="left: 8 GPUs   right (hatched): 16 GPUs")
ax2.set_xticks(list(x), [lbl for _, lbl, _ in variants], rotation=18, ha="right", fontsize=8)
ax2.set_ylabel("ms/step")
ax2.set_title("Pressure-solver ablation at the inter-node points", fontsize=10)
ax2.legend(fontsize=8, frameon=False)
ax2.grid(axis="x", visible=False)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "snellius_gpu.png"), dpi=150)
print("snellius_gpu.png")
