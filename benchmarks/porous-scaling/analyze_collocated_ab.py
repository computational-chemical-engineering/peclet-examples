#!/usr/bin/env python
"""Verdict table for the collocated second-order A/B (snellius/collocated_ab_gpu.sh).

    python analyze_collocated_ab.py results/snellius-h100

Reads colcmp_R*_<variant>.json and reports, per variant: the permeability against the staggered
cut-cell reference k_inf, the observed order of that error, the pressure iterations per step and
the wall cost. The question it settles: does mode 9 hold a small, monotone (ideally 2nd-order)
error on a BED at cut-cell iteration counts, and does the ghost projection over-carry the throats?
"""
import glob
import json
import os
import sys

import numpy as np

d = sys.argv[1] if len(sys.argv) > 1 else "results/snellius-h100"
VAR = ["stag_cutcell", "col_mode0", "col_mode9", "col_ghost"]
runs = {}
for f in glob.glob(os.path.join(d, "colcmp_R*.json")):
    j = json.load(open(f))
    base = os.path.basename(f)[len("colcmp_R"):-len(".json")]
    R, var = base.split("_", 1)
    runs.setdefault(var, {})[int(R)] = j
if not runs:
    raise SystemExit(f"no colcmp_R*.json under {d}")
Rs = sorted({r for v in runs.values() for r in v})

def k(var, R):
    j = runs.get(var, {}).get(R)
    m = (j or {}).get("march") or {}
    return m.get("k_over_R2"), m.get("converged"), (j or {}).get("pressure_iters_per_step"), \
        (j or {}).get("ms_per_step"), m.get("steps")

# reference: the two finest CONVERGED staggered cut-cell rungs, Richardson-extrapolated
ref = [(R, k("stag_cutcell", R)[0]) for R in Rs
       if k("stag_cutcell", R)[0] is not None and k("stag_cutcell", R)[1]]
if len(ref) >= 3:
    (R1, k1), (R2, k2), (R3, k3) = ref[-3:]
    with np.errstate(all="ignore"):
        p = np.log(abs((k1 - k2) / (k2 - k3))) / np.log(R2 / R1)
    kinf = k3 + (k3 - k2) / ((R3 / R2) ** p - 1.0)
    print(f"reference: staggered cut-cell, observed order p={p:.2f}, "
          f"Richardson k_inf = {kinf:.6f}  (finest rung R={R3}: {k3:.6f})")
elif ref:
    kinf = ref[-1][1]
    print(f"reference: staggered cut-cell finest rung R={ref[-1][0]}, k_inf = {kinf:.6f}")
else:
    raise SystemExit("no converged staggered cut-cell rung to reference against")

for var in VAR:
    if var not in runs:
        continue
    print(f"\n=== {var} ===")
    print(f"{'R':>4} {'grid':>6} {'k/R^2':>11} {'err %':>9} {'order':>7} "
          f"{'p.iters':>8} {'ms/step':>9} {'steps':>7}  conv")
    prev = None
    for R in Rs:
        kk, conv, it, ms, st = k(var, R)
        if kk is None:
            continue
        e = 100.0 * (kk - kinf) / kinf
        o = ""
        if prev is not None and abs(e) > 0 and abs(prev[1]) > 0:
            o = f"{np.log(abs(prev[1] / e)) / np.log(R / prev[0]):+.2f}"
        prev = (R, e)
        g = runs[var][R]["global"][0]
        print(f"{R:>4} {g:>6} {kk:>11.6f} {e:>+9.3f} {o:>7} {it:>8.1f} {ms:>9.1f} "
              f"{st if st else '-':>7}  {'yes' if conv else 'CAP'}")

print("\nWhat to look for:")
print("  col_mode0  first order (|err| halving per doubling of R) -- the known baseline")
print("  col_mode9  second order, or at least a small monotone band, at ~stag_cutcell iterations")
print("  col_ghost  watch the COARSE rungs: a positive err that grows as R falls is the throat")
print("             over-carry; and compare p.iters against stag_cutcell (phase A measured ~6x)")
