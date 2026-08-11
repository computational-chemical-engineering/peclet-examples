#!/usr/bin/env python
"""Figures for the channel-DNS weak-scaling benchmark.

Reads results/snellius-h100/chan_np*.json (written by snellius/chan_weak_gpu.sh) and writes:

    weak_scaling.png    weak-scaling efficiency + aggregate throughput vs GPU count
    channel_phases.png  where the step goes: per-phase breakdown, pressure iterations,
                        global-reduction time and count
    channel_levers.png  the ablation at the largest inter-node point (only if those JSONs exist)

Repeat draws (chan_np8_r2.json, ...) are all plotted; the line follows their median.
Missing points are skipped, so this runs on a partial sweep.
"""
import glob
import json
import os
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results", "snellius-h100")

BLUE, ORANGE, AQUA, YELLOW, PINK = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "font.size": 10,
    "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
})

GPUS_PER_NODE = 4


def load_sweep(prefix="chan_np"):
    """{N: [record, ...]} over all draws of each rank count (base run + _r2, _r3, ...)."""
    out = {}
    for f in sorted(glob.glob(os.path.join(RES, prefix + "*.json"))):
        stem = os.path.basename(f)[len(prefix):-len(".json")]
        head = stem.split("_")[0]
        if not head.isdigit() or len(stem.split("_")) > 2:  # skip levers (np8_cpg, np8_mg4, ...)
            continue
        if len(stem.split("_")) == 2 and not stem.split("_")[1].startswith("r"):
            continue
        out.setdefault(int(head), []).append(json.load(open(f)))
    return out


def med(recs, key):
    return statistics.median(r[key] for r in recs)


def phase(rec, name, stat="max"):
    return 1e3 * rec["phase_seconds_per_step"][name][stat]


# `refine_np*` (the production ladder: fixed physical box, refined with the GPU count) is the
# headline sweep; `chan_np*` (fixed cross-section, elongated box) is the stress test.
PREFIX = "refine_np" if glob.glob(os.path.join(RES, "refine_np*.json")) else "chan_np"
runs = load_sweep(PREFIX)
if not runs:
    raise SystemExit(f"no results in {RES} — run snellius/chan_weak_gpu.sh refine first")
print(f"[sweep] {PREFIX}*  ({len(runs)} rank counts)")
N = sorted(runs)
ms = [med(runs[n], "ms_per_step") for n in N]
agg = [med(runs[n], "mcells_per_s") for n in N]
# Weak efficiency from throughput PER GPU, not from ms/step. On the refine ladder the cells/GPU
# cannot be held exactly constant (see snellius/chan_weak_gpu.sh), and this normalisation corrects
# for that exactly; on a constant-size sweep it is identical to ms[0]/ms.
tp = [a / n for a, n in zip(agg, N)]
eff = [100 * t / tp[0] for t in tp]
pg = [runs[n][0]["cells"] / n / 1e6 for n in N]
per_gpu = f"{min(pg):.0f}-{max(pg):.0f}" if max(pg) - min(pg) > 1 else f"{pg[0]:.0f}"

# ---- figure 1: the curve ------------------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

ax1.plot(N, eff, "o-", color=BLUE, lw=2, ms=6, label="peclet.flow")
for n in N:  # every individual draw, as the honest spread
    for r in runs[n]:
        ax1.plot([n], [100 * (r["mcells_per_s"] / n) / tp[0]], "o", ms=3.5, mfc="none", mec=BLUE, mew=1)
ax1.axhline(100, ls="--", c=INK2, lw=0.8, label="ideal")
if max(N) > GPUS_PER_NODE:
    ax1.axvspan(GPUS_PER_NODE * 1.15, max(N) * 1.15, color=ORANGE, alpha=0.06)
    ax1.text(GPUS_PER_NODE * 1.4, 8, "multi-node", fontsize=8, color=ORANGE)
ax1.set_xscale("log", base=2)
ax1.set_xticks(N, [str(n) for n in N])
ax1.set_xlabel(f"H100 GPUs ({per_gpu} Mcells/GPU; {GPUS_PER_NODE} GPUs/node)")
ax1.set_ylabel("weak-scaling efficiency [%]")
ax1.set_ylim(0, 112)
ax1.set_title("Channel DNS weak scaling", fontsize=10)
ax1.legend(fontsize=8, frameon=False, loc="lower left")
for n, e, m in zip(N, eff, ms):
    ax1.annotate(f"{e:.0f}%\n{m:.0f} ms", (n, e), textcoords="offset points", xytext=(0, 9),
                 ha="center", fontsize=7.5, color=INK2)

ax2.plot(N, agg, "o-", color=BLUE, lw=2, ms=6, label="peclet.flow")
ax2.plot(N, [agg[0] * n / N[0] for n in N], ":", c=INK2, lw=1.2, label="ideal (linear)")
ax2.set_xscale("log", base=2)
ax2.set_yscale("log")
ax2.set_xticks(N, [str(n) for n in N])
ax2.set_xlabel("H100 GPUs")
ax2.set_ylabel("aggregate Mcell-updates/s")
ax2.set_title(f"Throughput — {agg[-1] / 1e3:.2f} Gcell/s on {N[-1]} GPUs", fontsize=10)
ax2.legend(fontsize=8, frameon=False, loc="upper left")

fig.tight_layout()
fig.savefig(os.path.join(HERE, "weak_scaling.png"), dpi=150)
print("weak_scaling.png")

# ---- figure 2: where the step goes ---------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

x = range(len(N))
bottom = [0.0] * len(N)
for name, col, lbl in (("predictor", AQUA, "predictor (ghosts, advection, stencils)"),
                       ("momentum", YELLOW, "momentum (implicit diffusion)"),
                       ("projection", BLUE, "projection (pressure solve)")):
    vals = [statistics.median(phase(r, name) for r in runs[n]) for n in N]
    ax1.bar(x, vals, 0.62, bottom=bottom, color=col, edgecolor=SURFACE, linewidth=1.5, label=lbl)
    bottom = [b + v for b, v in zip(bottom, vals)]
red = [statistics.median(phase(r, "pressure_allreduce") for r in runs[n]) for n in N]
cfr = [statistics.median(phase(r, "cfr") for r in runs[n]) for n in N]
ax1.plot(x, [r + c for r, c in zip(red, cfr)], "o-", color=ORANGE, lw=2, ms=5,
         label="of which: global reductions")
ax1.set_xticks(list(x), [str(n) for n in N])
ax1.set_xlabel("H100 GPUs")
ax1.set_ylabel("ms / step (rank-max)")
ax1.set_title("Where the step goes", fontsize=10)
ax1.legend(fontsize=7.5, frameon=False, loc="upper left")
ax1.grid(axis="x", visible=False)

it = [med(runs[n], "pressure_iters_per_step") for n in N]
ax2.plot(N, it, "o-", color=BLUE, lw=2, ms=6, label="pressure iterations / step")
ax2.set_xscale("log", base=2)
ax2.set_xticks(N, [str(n) for n in N])
ax2.set_xlabel("H100 GPUs")
ax2.set_ylabel("pressure iterations / step", color=BLUE)
ax2.set_ylim(0, max(it) * 1.6)
ax2.set_title("Algorithm vs communication", fontsize=10)
axb = ax2.twinx()
axb.plot(N, [100 * (r + c) / m for r, c, m in zip(red, cfr, ms)], "s--", color=ORANGE, lw=1.8, ms=5)
axb.set_ylabel("global reductions [% of step]", color=ORANGE)
axb.set_ylim(0, max(1.0, max(100 * (r + c) / m for r, c, m in zip(red, cfr, ms)) * 1.8))
axb.grid(False)
ax2.plot([], [], "s--", color=ORANGE, label="global reductions [% of step]")
ax2.legend(fontsize=8, frameon=False, loc="upper left")

fig.tight_layout()
fig.savefig(os.path.join(HERE, "channel_phases.png"), dpi=150)
print("channel_phases.png")

# ---- figure 3: lever ablation (optional) ---------------------------------------------------------
LEVERS = [("", "default", BLUE), ("_amg", "agglomerated\nbottom solve", AQUA),
          ("_decomp", "coarse-first\ndecomposition", PINK),
          ("_cpg", "CPG forcing", YELLOW), ("_meanall", "mean removal:\nall levels", "#9a7bd6"),
          ("_mg4", "MG depth 4", "#7a9ad6"), ("_mg6", "MG depth 6", "#c07bd6"),
          ("_hoststage", "host-staged\nhalo", ORANGE)]
for NL in (n for n in (32, 16, 8) if n in runs):
    have = [(s, lbl, c) for s, lbl, c in LEVERS
            if os.path.exists(os.path.join(RES, f"{PREFIX}{NL}{s}.json"))]
    if len(have) < 3:   # two bars is a table, not a figure
        continue
    vals = [json.load(open(os.path.join(RES, f"{PREFIX}{NL}{s}.json")))["ms_per_step"]
            for s, _, _ in have]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(range(len(have)), vals, 0.6, color=[c for _, _, c in have],
           edgecolor=SURFACE, linewidth=2)
    for i, v in enumerate(vals):
        ax.annotate(f"{v:.0f}\n{v / vals[0] - 1:+.1%}" if i else f"{v:.0f}", (i, v),
                    textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8)
    ax.set_xticks(range(len(have)), [lbl for _, lbl, _ in have], fontsize=8)
    ax.set_ylabel("ms / step")
    ax.set_title(f"Solver-configuration ablation at {NL} GPUs", fontsize=10)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "channel_levers.png"), dpi=150)
    print(f"channel_levers.png (N={NL})")
    break

# ---- console summary ----------------------------------------------------------------------------
print(f"\n{'GPUs':>5} {'ms/step':>9} {'eff':>6} {'Mcell/s':>9} {'iters':>6} {'sweeps':>7} "
      f"{'allred ms':>10} {'allred/step':>12} {'draws':>6}")
for n, m, e, a, i in zip(N, ms, eff, agg, it):
    r = runs[n][0]
    print(f"{n:5d} {m:9.1f} {e:5.0f}% {a:9.0f} {i:6.1f} "
          f"{med(runs[n], 'momentum_sweeps_per_step'):7.1f} "
          f"{statistics.median(phase(x_, 'pressure_allreduce') for x_ in runs[n]):10.1f} "
          f"{r['phase_seconds_per_step']['pressure_allreduce_count']['max']:12.0f} {len(runs[n]):6d}")
