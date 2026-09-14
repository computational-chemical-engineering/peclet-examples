#!/usr/bin/env python
"""Grow the unit cell of the scaling study: a periodic random sphere packing, with `peclet.dem`.

The artifact is the SPHERE LIST (centres + scales, sphere radius R = 1), not an SDF grid: every
rank of the flow benchmark samples the analytic union-of-spheres SDF over its own block, so one
packing serves any resolution and any rank count, and nothing global is ever gathered.

The cell is CUBIC and periodic, because the weak ladder tiles it: rung N is N exact copies of this
cell, so the permeability is one number that every rung must reproduce.

Sizing: the box follows from the resolution the study runs at. `RCELLS` sphere radii in cells at
the reference grid `GN` gives a box of GN/RCELLS radii, and the sphere count follows from the
target solid fraction. The default R = 18 cells sits above the R >= 16 at which the cut-cell
permeability is converged to four digits (peclet-examples porous-scaling refine ladder), so the
physics gate is a statement about the solver and not about an under-resolved bed.

    python make_bed.py                       # 384-cell reference grid, R = 18 cells, phi = 0.45

Env:
    GN        reference grid edge in cells (default 384)
    RCELLS    sphere radius in cells at that grid (default 18)
    PHI       target solid fraction (default 0.45)
    SEED      RNG seed for the initial positions (default 0)
    DT RATE   growth step / exponential growth rate (default 0.01 / 0.3)
    RELAX     relaxation steps after growth completes (default 400)
    ITERS     XPBD solver iterations, velocity + position (default 100)
    OUT       output npz (default bed_phi<phi>_r<rcells>_s<seed>.npz)
"""
import os
import sys
import time

import numpy as np

from peclet import dem

GN = int(os.environ.get("GN", 384))
RCELLS = float(os.environ.get("RCELLS", 18))
PHI = float(os.environ.get("PHI", 0.45))
SEED = int(os.environ.get("SEED", 0))
DT = float(os.environ.get("DT", 0.01))
RATE = float(os.environ.get("RATE", 0.3))
RELAX = int(os.environ.get("RELAX", 400))
ITERS = int(os.environ.get("ITERS", 100))

edge = GN / RCELLS                      # cubic box side, in sphere radii (R = 1)
box = np.array([edge, edge, edge])
vol_sphere = 4.0 / 3.0 * np.pi
N = int(round(PHI * box.prod() / vol_sphere))
phi_actual = N * vol_sphere / box.prod()
OUT = os.environ.get("OUT", f"bed_phi{PHI:g}_r{RCELLS:g}_s{SEED}.npz")

print(f"[bed] peclet.dem {dem.__version__} ({dem.execution_space})", flush=True)
print(f"[bed] reference grid {GN}^3 at R={RCELLS:g} cells -> cubic box {edge:.4f} R, "
      f"N={N} spheres, phi={phi_actual:.4f} (target {PHI}), seed={SEED}", flush=True)

sim = dem.Simulation(N)
sim.initialize_shape("sphere", radius=1.0)
half = box / 2.0
sim.set_domain(tuple(-half), tuple(half))
sim.set_periodic(True, True, True)
sim.set_gravity((0.0, 0.0, 0.0))
sim.set_material_params(0.0, 0.0, 0.0)   # inelastic: kinetic energy drains, the packing settles
sim.set_solver_iterations(ITERS, ITERS)

rng = np.random.default_rng(SEED)
pos = np.empty((N, 4), np.float32)
pos[:, :3] = rng.uniform(-half, half, (N, 3))
pos[:, 3] = 1.0                          # the w column is the INVERSE MASS, not a coordinate
sim.set_positions(pos)
sim.set_velocities(np.zeros((N, 3), np.float32))
sim.set_scales(np.ones(N, np.float32))

grow_steps = int(np.ceil(np.log(1.0 / 0.05) / (RATE * DT)))
sim.set_growth_params(RATE, 0.05)
sim.set_dt(DT)
t0 = time.time()
for _ in range(grow_steps + RELAX):
    sim.step()
t1 = time.time()

ov, gf = sim.max_overlap, sim.growth_factor
p = np.asarray(sim.get_positions()).reshape(-1, 3).astype(np.float64)
sc = np.asarray(sim.get_scales()).astype(np.float64)
p = (p + half) % box                     # store in [0, box)
print(f"[bed] {grow_steps}+{RELAX} steps in {t1 - t0:.1f}s  growth_factor={gf:.4f}  "
      f"max_overlap/R={ov:.5f}", flush=True)
if gf < 0.999:
    sys.exit(f"FATAL: growth did not complete (factor {gf})")
if ov > 0.05:
    sys.exit(f"FATAL: residual overlap {ov} > 5% of R — the packing is not converged")

# Independent union-volume check — does NOT trust the simulation's own overlap report. A packing
# whose contact solve was silently inert keeps a plausible max_overlap while its spheres
# interpenetrate, and then loses solid volume to the overlaps: the voxelised union fraction falls
# below the analytic phi. 8 voxels per radius.
dx = 0.125
dims = np.maximum((box / dx).astype(int), 1)
occ = np.zeros(dims, bool)
nb = int(np.ceil(sc.max() / dx)) + 1
for (cx, cy, cz), r in zip(p, sc):
    i0 = np.floor(np.array([cx, cy, cz]) / dx).astype(int)
    sl = [np.arange(i0[k] - nb, i0[k] + nb + 2) for k in range(3)]
    gx, gy, gz = np.meshgrid(*[(a + 0.5) * dx for a in sl], indexing="ij")
    m = (gx - cx) ** 2 + (gy - cy) ** 2 + (gz - cz) ** 2 <= r * r
    occ[np.ix_(*[a % dims[k] for k, a in enumerate(sl)])] |= m
phi_vox = occ.mean()
print(f"[bed] independent voxel solid fraction={phi_vox:.4f} (analytic {phi_actual:.4f})", flush=True)
if abs(phi_vox - phi_actual) > 0.02:
    sys.exit(f"FATAL: voxel fraction {phi_vox:.4f} != analytic {phi_actual:.4f} — the spheres "
             f"interpenetrate; the DEM contact solve did not act. No packing written.")

np.savez(OUT, centers=p, scales=sc, box=box, radius=1.0, phi=phi_actual, phi_voxel=phi_vox,
         seed=SEED, ref_grid=GN, rcells=RCELLS, nspheres=N, periodic=True,
         dem_version=dem.__version__)
print(f"[out] {OUT}", flush=True)
sys.stdout.flush()
os._exit(0)   # skip the Kokkos atexit teardown abort
