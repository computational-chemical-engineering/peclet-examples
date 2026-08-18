#!/usr/bin/env python
"""Constructed STRESS bed for the ghost-projection march: a periodic simple-cubic sphere lattice
whose every neighbour pair is near-tangent by a controlled gap. Same npz schema as pack_bed.py,
so spheres_bench.py consumes it unchanged.

The random beds put a THIN TAIL of near-tangent pairs into a huge box (the Snellius np=16/32
rungs); this puts the whole distribution at the tail in a box the workstation GPU can hold.

    python make_lattice_bed.py OUT.npz [n_per_axis] [gap_in_R] [jitter_in_R]
"""
import sys

import numpy as np

out = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
gap = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01
jit = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0

# spacing 2 R-units (touching spheres of unit radius); radius shrunk so the surface gap is `gap`
box = np.array([2.0*n]*3)
r = 1.0 - 0.5*gap - 0.5*jit          # jitter can only close gaps: keep them non-overlapping
g = (np.arange(n) + 0.5)*2.0
C = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3)
if jit:
    rng = np.random.default_rng(11)
    C = C + jit*(rng.random(C.shape) - 0.5)
C = np.mod(C, box)
scales = np.full(len(C), r)
phi = len(C)*(4.0/3.0)*np.pi*r**3/np.prod(box)
gn = int(round(16*box[0]))            # the reference rung grid = R 16 cells
np.savez(out, centers=C, scales=scales, box=box, phi=phi, seed=900 + n,
         gnx=gn, gny=gn, gnz=gn)
print(f"{out}: {len(C)} spheres, box {box}, r={r:.4f}, phi={phi:.4f}, "
      f"nominal surface gap {gap:.4f} R (jitter {jit} R), rung grid {gn}^3")
