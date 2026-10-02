"""Drift statistics (t >= 30), coalescence events and min gap for run_single.py outputs.
Usage: python summarise.py run_a1 [run_a2 ...]   (reads series.json, else ckpt.npz)"""
import json, os, sys
import numpy as np
for d in sys.argv[1:]:
    f = os.path.join(d, "series.json")
    ser = json.load(open(f)) if os.path.exists(f) else json.loads(str(np.load(os.path.join(d, "ckpt.npz"))["series"]))
    t = np.array([r["t"] for r in ser]); dr = np.array([r["drift"] for r in ser])
    n5 = np.array([r["n_regions"] for r in ser]); n3 = np.array([r["n_regions_1e-3"] for r in ser])
    gap = np.array([r["min_gap"] for r in ser])
    m = t >= 30 - 1e-9
    U0 = {"run_a1": 1.0264, "run_a2": 1.0363}.get(os.path.basename(d.rstrip("/")), np.nan)
    ev = int(np.sum(np.diff(n5) < 0) and -np.sum(np.minimum(np.diff(n5), 0)))
    first = t[np.argmax(n5 < 8)] if (n5 < 8).any() else None
    print(f"{d}: t_end {t[-1]:.1f}; drift(t>=30) {dr[m].mean():.4f} +- {dr[m].std():.4f} (n={m.sum()}), "
          f"U/U0 {dr[m].mean()/U0:.3f}; regions(C<0.5) min {n5.min()} final {n5[-1]}, "
          f"merge events {ev}, first <8 at t={first}; regions(1-C>1e-3) min {n3.min()}; "
          f"min gap {np.nanmin(gap):.3f} D at t={t[np.nanargmin(gap)]:.0f}; "
          f"dV {ser[-1]['gas_volume']/ser[0]['gas_volume']-1:+.1e}")
