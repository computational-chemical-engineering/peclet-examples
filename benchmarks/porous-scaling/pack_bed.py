#!/usr/bin/env python
"""DEM packing stage of the porous-scaling study: grow spheres in a periodic box to a target
solid fraction with `peclet.dem` (XPBD, growth mode), and save the sphere list (centers + scales,
sphere radius = 1) as the geometry artifact the flow benchmark rebuilds its SDF from.

The artifact is the SPHERE LIST, not an SDF grid: the flow side samples the analytic union-of-
spheres SDF rank-locally at whatever resolution the rung needs, so one packing serves a whole
refinement ladder and nothing global is ever gathered.

Single GPU (or CPU backend); seconds up to ~100k spheres. Run per upscale rung (seeded), once for
the refine ladder.

Env (all optional):
    GNX GNY GNZ  target flow grid of the rung (default 256^3) -- with RCELLS this sets the box
    RCELLS       sphere radius in flow-grid cells (default 16) => box = (GNX,GNY,GNZ)/RCELLS
    PHI          target solid fraction (default 0.50)
    SEED         RNG seed for initial positions (default 1)
    DT RATE      growth step / exponential growth rate (default 0.01 / 0.3)
    RELAX        extra relaxation steps after growth completes (default 200)
    ITERS        XPBD solver iterations, velocity+position (default 100)
    OUT          output npz (default packing_<gnx>x<gny>x<gnz>_r<rcells>_phi<phi>_s<seed>.npz)
"""
import os
import sys
import time

import numpy as np

sys.path.append(os.environ.get("DEM_BUILD", "/home/frankp/Codes/suite/dem/build"))
from peclet import dem  # noqa: E402

GNX = int(os.environ.get("GNX", 256))
GNY = int(os.environ.get("GNY", 256))
GNZ = int(os.environ.get("GNZ", 256))
RCELLS = float(os.environ.get("RCELLS", 16))
PHI = float(os.environ.get("PHI", 0.50))
SEED = int(os.environ.get("SEED", 1))
DT = float(os.environ.get("DT", 0.01))
RATE = float(os.environ.get("RATE", 0.3))
RELAX = int(os.environ.get("RELAX", 200))
ITERS = int(os.environ.get("ITERS", 100))

box = np.array([GNX, GNY, GNZ]) / RCELLS  # box in units of the sphere radius (R = 1)
vol_sphere = 4.0 / 3.0 * np.pi
N = int(round(PHI * box.prod() / vol_sphere))
phi_actual = N * vol_sphere / box.prod()
OUT = os.environ.get(
    "OUT", f"packing_{GNX}x{GNY}x{GNZ}_r{RCELLS:g}_phi{PHI:g}_s{SEED}.npz"
)

print(f"[pack] grid {GNX}x{GNY}x{GNZ} rcells={RCELLS:g} -> box {box[0]:.2f}x{box[1]:.2f}x"
      f"{box[2]:.2f} R-units, N={N} spheres, phi={phi_actual:.4f} (target {PHI}) seed={SEED}",
      flush=True)

sim = dem.Simulation(N)
sim.initialize(shape_type=1, radius=1.0)
half = box / 2.0
sim.set_domain(tuple(-half), tuple(half))
sim.enable_periodicity(True, True, True)
sim.set_gravity(0.0, 0.0, 0.0)
sim.set_material_params(0.0, 0.0, 0.0)  # inelastic: kinetic energy is drained, packing settles
sim.set_solver_iterations(ITERS, ITERS)

rng = np.random.default_rng(SEED)
pos = np.empty((N, 4), np.float32)
pos[:, :3] = rng.uniform(-half, half, (N, 3))
pos[:, 3] = 1.0
sim.set_positions(pos)
sim.set_velocities(np.zeros((N, 4), np.float32))
sim.set_scales(np.ones(N, np.float32))

grow_steps = int(np.ceil(np.log(1.0 / 0.05) / (RATE * DT)))
sim.set_growth_params(RATE, 0.05)
t0 = time.time()
asleep_max = 0
for i in range(grow_steps + RELAX):
    sim.step(DT)
    if i % 100 == 0:
        asleep_max = max(asleep_max, sim.num_asleep())
t1 = time.time()

ov = sim.get_max_overlap()
gf = sim.get_growth_factor()
p = np.asarray(sim.get_positions()).reshape(-1, 3).astype(np.float64)
s = np.asarray(sim.get_scales()).astype(np.float64)
p += half  # store in [0, box)
p %= box
print(f"[pack] {grow_steps}+{RELAX} steps in {t1 - t0:.1f}s "
      f"({1e3 * (t1 - t0) / (grow_steps + RELAX):.1f} ms/step)  growth_factor={gf:.4f}  "
      f"max_overlap/R={ov:.5f}  max_asleep={asleep_max}", flush=True)
if gf < 0.999:
    sys.exit(f"FATAL: growth did not complete (factor {gf})")
if ov > 0.05:
    sys.exit(f"FATAL: residual overlap {ov} > 5% of R -- packing not converged")

np.savez(OUT, centers=p, scales=s, box=box, radius=1.0, phi=phi_actual, seed=SEED,
         gnx=GNX, gny=GNY, gnz=GNZ, rcells=RCELLS)
print(f"[out] {OUT}", flush=True)
sys.stdout.flush()
os._exit(0)  # skip Kokkos atexit teardown abort
