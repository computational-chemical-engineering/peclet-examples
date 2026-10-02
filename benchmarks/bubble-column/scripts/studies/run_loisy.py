"""Loisy, Naso & Spelt (JFM 816, 2017) free array, case E1: 8 bubbles in a triply periodic cube,
phi = 3.79 % (box 4.8 D, 96^3 cells, D/h = 20). Reuses the bubble-column driver with the geometry
swapped and the y walls removed. Reference (their fig. 21, Nb = 8): U/U0 ~ 0.80 at phi = 3.8 %."""
import os, sys
import numpy as np
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, SCRIPTS)
import case
L = 4.8
N = int(os.environ.get("LOISY_N", "96"))
case.LX = case.LY = case.LZ = L
case.CELLS_PER_D = N / L
case.NX = case.NY = case.NZ = N
case.H = L / N
case.NB = 8
SEED = int(os.environ.get("LOISY_SEED", "1"))
def centres():
    rng = np.random.default_rng(SEED)
    pts = []
    while len(pts) < case.NB:
        c = rng.random(3) * L
        ok = True
        for q in pts:
            d = np.abs(c - q); d = np.minimum(d, L - d)
            if np.linalg.norm(d) < 1.6:          # interfaces >= 0.6 D apart initially
                ok = False; break
        if ok: pts.append(c)
    return np.array(pts)
case.bubble_centres = centres
case.VOID_FRACTION = case.NB * np.pi / 6 / L**3
import peclet.flow as pf
_orig_bc = pf.Solver.set_domain_bc
def _no_walls(self, face, kind, *a, **k):        # triply periodic: drop the column's y walls
    if face in ("-y", "+y") and kind == "wall":
        return
    return _orig_bc(self, face, kind, *a, **k)
pf.Solver.set_domain_bc = _no_walls
import run_peclet
run_peclet.S = case.CELLS_PER_D   # the driver scales with cells per D
run_peclet.NX = run_peclet.NY = run_peclet.NZ = N
run_peclet.main()
