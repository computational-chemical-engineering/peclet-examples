#!/usr/bin/env python
"""Figures for the workstation part of the parallel-scaling study.

Reads results/workstation/*.json (bench_workstation.sh, bench_references.sh) and the pre-fix
archive results/workstation-prefix-alignment/, writes:
  workstation_mix.png      - hybrid MPI x OpenMP mix at fixed 192^3 (throughput + phase split)
  workstation_weak.png     - weak scaling 2.1M cells/rank: peclet vs CaNS vs OpenFOAM
  workstation_alignfix.png - before/after the coarsenAlignment cap
"""
import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results", "workstation")  # final-solver runs (headline figures)
# the alignment-fix before/after pair, both measured with the SAME (pre-tolerance-stop) solver:
PRE = os.path.join(HERE, "results", "workstation-prefix-alignment")
ALIGNPOST = os.path.join(HERE, "results", "workstation-alignfix-post")

# validated reference palette (light mode), fixed slot order
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "font.size": 10,
    "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
})


def load(dirname, pattern):
    out = []
    for f in sorted(glob.glob(os.path.join(dirname, pattern))):
        with open(f) as fh:
            d = json.load(fh)
        d["_file"] = os.path.basename(f)
        out.append(d)
    return out


def phase_ms(d, key):
    return 1e3 * d["phase_seconds_per_step"][key]["max"]


def mixkey(d):
    return f"{d['np']}×{int(d['omp_threads'] or 1)}"


# ---- 1: hybrid mix ----------------------------------------------------------------------------
mix = sorted(load(RES, "mix_r*.json"), key=lambda d: (d["np"], int(d["omp_threads"] or 1)))
if mix:
    labels = [mixkey(d) for d in mix]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
    thr = [d["mcells_per_s"] for d in mix]
    b = ax1.barh(labels, thr, color=BLUE, height=0.62)
    for r, v in zip(b, thr):
        ax1.text(v + 0.06, r.get_y() + r.get_height() / 2, f"{v:.1f}",
                 va="center", fontsize=9, color=INK2)
    ax1.set_xlabel("Mcell/s (higher is better)")
    ax1.set_title("Throughput by MPI×OpenMP mix, 192$^3$", fontsize=10)
    ax1.set_xlim(0, max(thr) * 1.18)
    ax1.grid(axis="y", visible=False)

    # phase split (parallel runs only -- the serial bar would squash the panel): projection is
    # shown net of the allreduce term so segments sum to the step
    par = [d for d in mix if not (d["np"] == 1 and int(d["omp_threads"] or 1) == 1)]
    plabels = [mixkey(d) for d in par]
    segs = [("predictor", BLUE), ("momentum", ORANGE), ("projection − allreduce", AQUA),
            ("pressure allreduce", YELLOW)]
    vals = {
        "predictor": [phase_ms(d, "predictor") for d in par],
        "momentum": [phase_ms(d, "momentum") for d in par],
        "projection − allreduce":
            [phase_ms(d, "projection") - phase_ms(d, "pressure_allreduce") for d in par],
        "pressure allreduce": [phase_ms(d, "pressure_allreduce") for d in par],
    }
    left = [0.0] * len(par)
    for name, col in segs:
        ax2.barh(plabels, vals[name], left=left, color=col, height=0.62,
                 label=name, edgecolor=SURFACE, linewidth=2)
        left = [a + b_ for a, b_ in zip(left, vals[name])]
    ax2.set_xlabel("ms/step (rank max)")
    ax2.set_title("Where the step goes (parallel mixes)", fontsize=10)
    ax2.legend(fontsize=8, frameon=False, loc="lower right")
    ax2.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "workstation_mix.png"), dpi=150)
    print("workstation_mix.png")

# ---- 2: weak scaling, three codes + GPU reference ---------------------------------------------
codes = [
    ("weak_np*.json", "peclet.flow", BLUE),
    ("cans_weak_np*.json", "CaNS", ORANGE),
    ("of_weak_np*.json", "OpenFOAM", AQUA),
]
have = {lbl: sorted(load(RES, pat), key=lambda d: d["np"]) for pat, lbl, _ in codes}
if all(have.values()):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
    for pat, lbl, col in codes:
        runs = have[lbl]
        nps = [d["np"] for d in runs]
        eff = [100.0 * runs[0]["ms_per_step"] / d["ms_per_step"] for d in runs]
        ax1.plot(nps, eff, "o-", color=col, lw=2, ms=5, label=lbl)
        thr = [d["mcells_per_s"] for d in runs]
        ax2.plot(nps, thr, "o-", color=col, lw=2, ms=5, label=lbl)
    ax1.axhline(100, ls="--", c=INK2, lw=0.8)
    for ax in (ax1, ax2):
        ax.set_xscale("log", base=2)
        nps = [d["np"] for d in have["peclet.flow"]]
        ax.set_xticks(nps, [str(n) for n in nps])
        ax.set_xlabel("MPI ranks (1 core each)")
        ax.legend(fontsize=8, frameon=False)
    ax1.set_ylabel("weak-scaling efficiency [%]")
    ax1.set_ylim(0, 112)
    ax1.set_title("Weak scaling, 2.1M cells/rank (one node)", fontsize=10)
    ax2.set_yscale("log")
    ax2.set_ylabel("aggregate Mcell/s")
    ax2.set_title("Absolute throughput (log scale)", fontsize=10)
    gpu = load(RES, "gpu_192.json")
    if gpu:
        g = gpu[0]["mcells_per_s"]
        ax2.axhline(g, ls=":", c=INK2, lw=1.2)
        ax2.annotate(f"1× RTX 5080 ({g:.0f})", (nps[0], g), textcoords="offset points",
                     xytext=(2, 5), fontsize=8, color=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "workstation_weak.png"), dpi=150)
    print("workstation_weak.png")

# ---- 3: the alignment fix, before/after -------------------------------------------------------
pre = {mixkey(d): d for d in load(PRE, "mix_r*.json") if d["np"] > 1}
post = {mixkey(d): d for d in load(ALIGNPOST, "mix_r*.json") if d["np"] > 1}
pre_w = {d["np"]: d for d in load(PRE, "weak_np*.json")}
post_w = {d["np"]: d for d in load(ALIGNPOST, "weak_np*.json")}
common = sorted((k for k in post if k in pre),
                key=lambda k: -int(k.split("×")[0]))
if common and 24 in pre_w:
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    labels = common + ["weak 24×1"]
    b_ms = [pre[k]["ms_per_step"] for k in common] + [pre_w[24]["ms_per_step"]]
    a_ms = [post[k]["ms_per_step"] for k in common] + [post_w[24]["ms_per_step"]]
    b_it = [pre[k]["pressure_iters_per_step"] for k in common] + \
           [pre_w[24]["pressure_iters_per_step"]]
    a_it = [post[k]["pressure_iters_per_step"] for k in common] + \
           [post_w[24]["pressure_iters_per_step"]]
    x = range(len(labels))
    w = 0.38
    r1 = ax.bar([i - w / 2 for i in x], b_ms, w, color=BLUE, label="before (natural-max align)",
                edgecolor=SURFACE, linewidth=2)
    r2 = ax.bar([i + w / 2 for i in x], a_ms, w, color=ORANGE, label="after (align cap 16)",
                edgecolor=SURFACE, linewidth=2)
    for r, it in zip(list(r1) + list(r2), b_it + a_it):
        ax.text(r.get_x() + r.get_width() / 2, r.get_height() * 1.03, f"{it:.0f} it",
                ha="center", fontsize=8, color=INK2)
    ax.set_yscale("log")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("ms/step (log)")
    ax.set_xlabel("MPI ranks × OpenMP threads (192$^3$; rightmost: weak 3072×128×128)")
    ax.set_title("The coarsenAlignment cap: step time and pressure iterations, before → after",
                 fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "workstation_alignfix.png"), dpi=150)
    print("workstation_alignfix.png")
