#!/usr/bin/env python
"""Generate the FoxBerry packed-bed geometry for the foxberry-scaling benchmark with `peclet.dem`.

FoxBerry's PackedBed case (FoxBerry/scaling/Scaling.cpp) places 5000 equal spheres at solid
holdup 0.45 inside the region (L - 8dx, H, D) = (0.98, 1, 1) of the unit box, shifted +4dx in x
so no particle center sits within 4 cells of the inlet/outlet.  The sphere radius follows from
the holdup:

    r = cbrt(0.45 * 0.98 / (5000 * 4/3 * pi)) = 0.0276171...   (D/dx = 22.09 at 400^3)

FoxBerry's own coordinate generator (seed 0) cannot be reproduced here, so the bed is grown with
peclet.dem instead (XPBD growth in a periodic box of the same region, same N, same radius, same
holdup) -- statistically equivalent, geometrically ours.  The artifact is the SPHERE LIST
(centers in units of the sphere radius, R = 1), exactly the `pack_bed.py` npz schema of the
porous-scaling study: the flow benchmark resamples the analytic union-of-spheres SDF rank-locally
at any resolution.

Env (all optional):
    NSPHERES  number of particles          (default 5000, the FoxBerry value)
    HOLDUP    solid fraction of the region (default 0.45)
    SEED      RNG seed for initial positions (default 0, matching FoxBerry's seed)
    PERIODIC  0 (default) = the FoxBerry region (0.98, 1, 1), bed shifted +4dx in x so it is
              periodic in y/z only and clipped at the inlet/outlet.
              1 = a TRIPLY-periodic bed filling the whole unit box, for BCMODE=periodic runs.
              A y/z-only bed run under fully periodic BCs has a broken geometric seam at x=0/1
              (a sphere clipped at one face does not continue at the other), so the two must
              match -- foxberry_bench.py refuses the mismatched combination.
    DT RATE RELAX ITERS   dem growth controls (pack_bed.py defaults)
    OUT       output npz (default results/packing_foxberry[_periodic]_n<N>_phi<H>_s<SEED>.npz)
"""
import os
import sys
import time

import numpy as np

sys.path.append(os.environ.get("DEM_BUILD", "/home/frankp/Codes/suite/dem/build"))
from peclet import dem  # noqa: E402

NSPH = int(os.environ.get("NSPHERES", 5000))
HOLDUP = float(os.environ.get("HOLDUP", 0.45))
SEED = int(os.environ.get("SEED", 0))
PERIODIC = int(os.environ.get("PERIODIC", 0))
DT = float(os.environ.get("DT", 0.01))
RATE = float(os.environ.get("RATE", 0.3))
RELAX = int(os.environ.get("RELAX", 200))
ITERS = int(os.environ.get("ITERS", 100))

# The particle region in physical units. FoxBerry's is (L - 8dx, H, D) at 400^3 = (0.98, 1, 1),
# with the bed shifted +4dx in x; the periodic variant fills the whole unit box instead.
REGION = np.array([1.0, 1.0, 1.0]) if PERIODIC else np.array([0.98, 1.0, 1.0])
vol_sphere = 4.0 / 3.0 * np.pi
r_phys = (HOLDUP * REGION.prod() / (NSPH * vol_sphere)) ** (1.0 / 3.0)
box = REGION / r_phys                     # packing box in units of the sphere radius (R = 1)
phi = NSPH * vol_sphere / box.prod()      # == HOLDUP by construction

_kind = "_periodic" if PERIODIC else ""
OUT = os.environ.get(
    "OUT", f"results/packing_foxberry{_kind}_n{NSPH}_phi{HOLDUP:g}_s{SEED}.npz")

print(f"[bed] {'TRIPLY-PERIODIC' if PERIODIC else 'FoxBerry (y/z-periodic)'}  N={NSPH} "
      f"holdup={HOLDUP} -> r={r_phys:.7f} (D/dx={2 * r_phys * 384:.2f} cells at 384^3, "
      f"{2 * r_phys * 400:.2f} at 400^3)  box={box[0]:.3f}x{box[1]:.3f}x{box[2]:.3f} R-units  "
      f"phi={phi:.4f}  seed={SEED}", flush=True)

sim = dem.Simulation(NSPH)
sim.initialize(shape_type=1, radius=1.0)
half = box / 2.0
sim.set_domain(tuple(-half), tuple(half))
sim.enable_periodicity(True, True, True)
sim.set_gravity(0.0, 0.0, 0.0)
sim.set_material_params(0.0, 0.0, 0.0)  # inelastic: kinetic energy drained, packing settles
sim.set_solver_iterations(ITERS, ITERS)

rng = np.random.default_rng(SEED)
pos = np.empty((NSPH, 4), np.float32)
pos[:, :3] = rng.uniform(-half, half, (NSPH, 3))
pos[:, 3] = 1.0
sim.set_positions(pos)
sim.set_velocities(np.zeros((NSPH, 4), np.float32))
sim.set_scales(np.ones(NSPH, np.float32))

grow_steps = int(np.ceil(np.log(1.0 / 0.05) / (RATE * DT)))
sim.set_growth_params(RATE, 0.05)
t0 = time.time()
for i in range(grow_steps + RELAX):
    sim.step(DT)
t1 = time.time()

ov = sim.get_max_overlap()
gf = sim.get_growth_factor()
p = np.asarray(sim.get_positions()).reshape(-1, 3).astype(np.float64)
s = np.asarray(sim.get_scales()).astype(np.float64)
p += half  # store in [0, box)
p %= box
print(f"[bed] {grow_steps}+{RELAX} steps in {t1 - t0:.1f}s  growth_factor={gf:.4f}  "
      f"max_overlap/R={ov:.5f}", flush=True)
if gf < 0.999:
    sys.exit(f"FATAL: growth did not complete (factor {gf})")
if ov > 0.05:
    sys.exit(f"FATAL: residual overlap {ov} > 5% of R -- packing not converged")

# Independent union-volume check (the porous-scaling lesson: do NOT trust the sim's own overlap
# report -- an inert contact pipeline loses solid volume to interpenetration). 8 voxels per R.
dx = 0.125
dims = np.maximum((box / dx).astype(int), 1)
occ = np.zeros(dims, bool)
nb = int(np.ceil(s.max() / dx)) + 1
for (cx, cy, cz), sc in zip(p, s):
    i0 = np.floor(np.array([cx, cy, cz]) / dx).astype(int)
    sl = [np.arange(i0[k] - nb, i0[k] + nb + 2) for k in range(3)]
    gx, gy, gz = np.meshgrid(*[(a + 0.5) * dx for a in sl], indexing="ij")
    m = (gx - cx) ** 2 + (gy - cy) ** 2 + (gz - cz) ** 2 <= sc * sc
    occ[np.ix_(*[a % dims[k] for k, a in enumerate(sl)])] |= m
phi_vox = occ.mean()
print(f"[bed] independent voxel solid fraction={phi_vox:.4f} (analytic {phi:.4f})", flush=True)
if abs(phi_vox - phi) > 0.02:
    sys.exit(f"FATAL: voxel fraction {phi_vox:.4f} != analytic {phi:.4f} -- spheres are "
             f"interpenetrating; the DEM contact solve did not act. NOT saving.")

os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
np.savez(OUT, centers=p, scales=s, box=box, radius=1.0, phi=phi, seed=SEED,
         region=REGION, r_phys=r_phys, holdup=HOLDUP, nspheres=NSPH,
         xperiodic=bool(PERIODIC))
print(f"[out] {OUT}", flush=True)
sys.stdout.flush()
os._exit(0)  # skip Kokkos atexit teardown abort
