#!/usr/bin/env python
"""Plots for the porous-scaling study from the per-rung JSONs.

  python plot_spheres.py results/snellius-h100

Produces (into the results dir):
  porous_weak.png    upscale ladder: per-GPU throughput + weak efficiency + iters/step, per IBM
  porous_refine.png  refine ladder: per-GPU throughput + iters/step + k(N) convergence, per IBM
"""
import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RES = sys.argv[1] if len(sys.argv) > 1 else "results/snellius-h100"


def load(pattern):
    out = {}
    for f in glob.glob(os.path.join(RES, pattern)):
        if "smoother" in f or "hoststage" in f:  # lever ablations, not ladder points
            continue
        d = json.load(open(f))
        out.setdefault(d["ibm"], []).append(d)
    for v in out.values():
        v.sort(key=lambda d: d["np"])
    return out


def sane_k(d):
    """March k usable for physics: present and physically plausible (diverged runs hit 1e57)."""
    m = d.get("march") or {}
    k = m.get("k_over_R2")
    return k if k is not None and 0 < k < 1 else None


def fit_order(Ns, vals):
    Ns = np.asarray(Ns, float)
    vals = np.asarray(vals, float)
    best = None
    for p in np.linspace(0.3, 4.0, 371):
        A = np.vstack([np.ones_like(Ns), Ns ** (-p)]).T
        coef, *_ = np.linalg.lstsq(A, vals, rcond=None)
        ssr = float(((vals - A @ coef) ** 2).sum())
        if best is None or ssr < best[0]:
            best = (ssr, float(p), float(coef[0]))
    return best[1], best[2]


COLOR = {"cutcell": "C0", "ghost": "C1"}

# ---- upscale ----------------------------------------------------------------------------------
weak = load("weak_np*.json")
if any(weak.values()):
    fig, ax = plt.subplots(1, 4, figsize=(16.5, 3.6))
    for ibm, runs in weak.items():
        if not runs:
            continue
        nps = [d["np"] for d in runs]
        pergpu = [d["mcells_per_s_per_rank"] for d in runs]
        ax[0].plot(nps, pergpu, "o-", color=COLOR[ibm], label=ibm)
        ax[1].plot(nps, [100 * p / pergpu[0] for p in pergpu], "o-", color=COLOR[ibm], label=ibm)
        ax[2].plot(nps, [d["pressure_iters_per_step"] for d in runs], "o-",
                   color=COLOR[ibm], label=ibm)
        # physics: per-rung bed permeability, CONVERGED marches only (ghost np>=16 diverges --
        # a documented open solver issue; its perf-phase points above remain valid)
        ks = [(d["np"], sane_k(d)) for d in runs
              if d.get("march", {}).get("converged") and sane_k(d)]
        if ks:
            kn, kv = zip(*ks)
            ax[3].plot(kn, kv, "o-", color=COLOR[ibm], label=ibm)
    ax[0].set_ylabel("Mcell/s per GPU")
    ax[1].set_ylabel("weak efficiency [%]")
    ax[1].axhline(100, color="k", lw=0.5)
    ax[2].set_ylabel("pressure iters/step")
    ax[3].set_ylabel("k / R$^2$  (per-rung bed)")
    for a in ax:
        a.set_xlabel("GPUs")
        a.set_xscale("log", base=2)
        a.legend()
        a.grid(alpha=0.3)
    fig.suptitle("Upscale weak scaling: DEM sphere bed, 256$^3$ cells/GPU")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "porous_weak.png"), dpi=150)
    print("wrote porous_weak.png")

# ---- refine -----------------------------------------------------------------------------------
ref = load("refine_np*.json")
if any(ref.values()):
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    for ibm, runs in ref.items():
        nps = [d["np"] for d in runs]
        Ns = [d["global"][0] for d in runs]
        pergpu = [d["mcells_per_s_per_rank"] for d in runs]
        ax[0].plot(nps, pergpu, "o-", color=COLOR[ibm], label=ibm)
        ax[1].plot(nps, [d["pressure_iters_per_step"] for d in runs], "o-",
                   color=COLOR[ibm], label=ibm)
        # k(N): converged marches filled, step-capped-but-plateaued (sane k) open markers;
        # the Richardson fit uses every sane point (the 1024^3 caps sit on the plateau).
        ks = [(d["global"][0], sane_k(d), bool(d["march"]["converged"])) for d in runs
              if sane_k(d)]
        ks.sort()
        if len(ks) >= 3:
            kn, kv, conv = zip(*ks)
            p, kinf = fit_order(kn, kv)
            ax[2].plot(kn, kv, "-", color=COLOR[ibm],
                       label=f"{ibm}: p={p:.1f}, k∞={kinf:.4g}")
            for n, v, c in ks:
                ax[2].plot([n], [v], "o", color=COLOR[ibm],
                           mfc=COLOR[ibm] if c else "white")
            ax[2].axhline(kinf, color=COLOR[ibm], lw=0.5, ls="--")
        elif ks:
            kn, kv, _ = zip(*ks)
            ax[2].plot(kn, kv, "o-", color=COLOR[ibm], label=ibm)
    ax[0].set_ylabel("Mcell/s per GPU")
    ax[0].set_xlabel("GPUs")
    ax[0].set_xscale("log", base=2)
    ax[1].set_ylabel("pressure iters/step")
    ax[1].set_xlabel("GPUs")
    ax[1].set_xscale("log", base=2)
    ax[2].set_ylabel("k / R$^2$")
    ax[2].set_xlabel("grid N (fixed bed)")
    for a in ax:
        a.legend()
        a.grid(alpha=0.3)
    fig.suptitle("Refine weak scaling: one physical bed, sphere R = 16→64 cells")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "porous_refine.png"), dpi=150)
    print("wrote porous_refine.png")
