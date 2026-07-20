#!/usr/bin/env python
"""Dosta et al. 2024 (CPC 296:109066) benchmark — Case 3: particle impact.

Steel ball (d = 20 mm, rho = 7200) dropped at 5 m/s onto a settled bed of M1 particles
(d = 2 mm, rho = 2500) in a 0.10 x 0.06 x 0.2 m box; 0.1 s simulated, ball height
recorded every 1 ms. Initial particle positions are the benchmark's shared
InitialCoordinates files, so every code starts from the identical state.

peclet-dem is an impulse-based (XPBD) solver: contacts are rigid at the velocity level
(restitution e + Coulomb friction mu), there is no Young's modulus and no stiffness-limited
time step. Materials are mapped as:
  grain-grain  e=0.5, mu=0.3   (M1-M1)
  grain-wall   e=0.4, mu=0.2   (M1-Steel; the ball-wall/ball-grain pairs are approximated
                                by these same values — single global pair material for now)
"""
import argparse
import os
import sys
import time

import numpy as np

from peclet import dem
from peclet.dem import build_wall_sdf

IC_DIR = (
    "/tmp/claude-1003/-home-frankp-Codes-suite/9e9b807a-7a8a-4948-a080-545a0f831797/"
    "scratchpad/dosta2024/SupplementaryMaterial/InitialCoordinates/Case 3 - Impact"
)

# Inner box surfaces from the benchmark wall mesh (walls 1 mm thick, floor 2 mm).
XLO, XHI = -0.05, 0.05
YLO, YHI = -0.03, 0.03
ZLO, ZHI = -0.0902431, 0.107757

RHO_M1, RHO_STEEL = 2500.0, 7200.0
G = 9.81


def box_sdf(p):
    """Positive in the void, negative in the wall (container convention)."""
    d = np.minimum(p[:, 0] - XLO, XHI - p[:, 0])
    d = np.minimum(d, np.minimum(p[:, 1] - YLO, YHI - p[:, 1]))
    d = np.minimum(d, p[:, 2] - ZLO)  # floor; top open (ZHI far above everything)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25, choices=[25, 50, 100], help="bed size in k")
    ap.add_argument("--dt", type=float, default=5e-5)
    ap.add_argument("--iters", type=int, nargs=2, default=[12, 8], help="pos vel iterations")
    ap.add_argument("--tend", type=float, default=0.1)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--seed-shift", type=float, default=0.0,
                    help="tiny z-shift of the ball start (repeatability ensembles)")
    ap.add_argument("--jacobi", action="store_true",
                    help="legacy count-averaged Jacobi velocity solve (disables GS/PGS statics)")
    args = ap.parse_args()

    d = np.loadtxt(f"{IC_DIR}/{args.n}KParticles.txt", skiprows=1).astype(np.float64)
    radii, pos = d[:, 0], d[:, 1:4]
    n = len(d)
    ball = int(np.argmax(radii))  # r = 0.01 row (last)
    assert radii[ball] == 0.01 and n == args.n * 1000 + 1
    pos[ball, 2] += args.seed_shift

    sim = dem.Simulation(n)
    r0 = 0.001  # canonical radius; per-particle scale multiplies it
    sim.set_sphere_shape(r0)
    sim.set_domain((XLO - 0.01, YLO - 0.01, ZLO - 0.01), (XHI + 0.01, YHI + 0.01, ZHI + 0.01))
    sim.enable_periodicity(False, False, False)

    wall = build_wall_sdf(box_sdf, ((XLO - 0.01, YLO - 0.01, ZLO - 0.01),
                                    (XHI + 0.01, YHI + 0.01, ZHI + 0.01)),
                          resolution=(144, 96, 256))
    wid = wall.add_to(sim, restitution=0.4, friction=0.2)
    # exact benchmark pair materials when the build supports them: 0 = M1 bed, 1 = steel
    per_pair = hasattr(sim, "set_pair_material")
    if per_pair:
        sim.set_pair_material(0, 0, 0.5, 0.3)   # M1-M1
        sim.set_pair_material(0, 1, 0.4, 0.2)   # M1-steel (ball and walls)
        sim.set_pair_material(1, 1, 0.6, 0.5)   # steel-steel (ball-floor)
        sim.set_wall_material_id(wid, 1)

    scales = (radii / r0).astype(np.float32)
    sim.set_positions(pos.astype(np.float32))
    sim.set_scales(scales)

    rho = np.where(radii > 0.005, RHO_STEEL, RHO_M1)
    m = rho * 4.0 / 3.0 * np.pi * radii**3
    sim.set_inv_mass((1.0 / m).astype(np.float32))
    inv_I = (1.0 / (0.4 * m * radii**2)).astype(np.float32)
    sim.set_inv_inertia(np.repeat(inv_I[:, None], 3, axis=1).astype(np.float32))

    v = np.zeros((n, 3), np.float32)
    v[ball, 2] = -5.0
    sim.set_velocities(v)
    if per_pair:
        ids = np.zeros(n, np.int32)
        ids[ball] = 1
        sim.set_material_ids(ids.tolist())

    sim.set_gravity(0.0, 0.0, -G)
    sim.set_material_params(0.5, 0.0, 0.3)  # M1-M1
    sim.set_solver_iterations(args.iters[0], args.iters[1])
    sim.set_thermostat(0.0, 0.0)
    if args.jacobi:
        sim.set_velocity_use_gs(False)
    if os.environ.get("NOSTAB"):
        sim.set_stabilization(False)

    nsteps = int(round(args.tend / args.dt))
    rec_every = max(1, int(round(1e-3 / args.dt)))
    ts, zs = [], []

    t0 = time.perf_counter()
    for i in range(nsteps + 1):
        if i % rec_every == 0:
            z = float(sim.get_positions()[ball, 2])
            ts.append(i * args.dt)
            zs.append(z)
        if i < nsteps:
            sim.step(args.dt)
    wall_s = time.perf_counter() - t0

    out = args.out or f"case3_{args.n}k_peclet{'_jac' if args.jacobi else ''}.npz"
    np.savez(out, t=np.array(ts), z=np.array(zs), wall_s=wall_s, dt=args.dt,
             iters=args.iters, n=n)
    print(f"n={n} dt={args.dt:g} steps={nsteps} wall={wall_s:.1f}s "
          f"({1e3 * wall_s / nsteps:.2f} ms/step)")
    print(f"z(t=0.03)={np.interp(0.03, ts, zs):+.4f}  z(end)={zs[-1]:+.4f}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
