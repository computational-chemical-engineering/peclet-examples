#!/usr/bin/env python
"""Dosta et al. 2024 benchmark — Case 2: rotating drum mixer.

Steel drum, R = 0.1 m about the y-axis, inner depth 0.06 m (y in [-0.03, 0.03]),
rotating at 2 rad/s (wall surface moves +z at +x, matching the LIGGGHTS reference:
rotate axis 0 1 0 period -3.14159). Bimodal bed from the shared InitialCoordinates:
30k M1 (r = 1 mm, rho = 2500) on top of 8k M2 (r = 2 mm, rho = 2000). 5 s simulated.

Outputs every 0.1 s: number of M1/M2 particles in Zone 1 (x>0, z>0) and Zone 2
(x<0, z<0), and the centres of mass of the M1 and M2 fractions (paper Figs 8, 9, A.12).

Grain-grain materials are per-pair in the benchmark (M1-M1 0.5/0.3, M1-M2 0.45/0.2,
M2-M2 0.4/0.4); until peclet-dem grows a pair table this uses one global (e, mu)
(default 0.45/0.25 — the contact-weighted middle) — pass --e/--mu to override.
Wall (steel) material: e = 0.4, mu = 0.2 (per-wall binary material, exact).
"""
import argparse
import time

import numpy as np

from peclet import dem
from peclet.dem import build_wall_sdf

IC = ("/tmp/claude-1003/-home-frankp-Codes-suite/9e9b807a-7a8a-4948-a080-545a0f831797/"
      "scratchpad/dosta2024/SupplementaryMaterial/InitialCoordinates/Case 2 - Mixer/"
      "PartCoordinates.txt")

R_DRUM, Y_HALF, OMEGA = 0.1, 0.03, 2.0


def drum_sdf(p):
    barrel = R_DRUM - np.sqrt(p[:, 0] ** 2 + p[:, 2] ** 2)
    caps = np.minimum(p[:, 1] + Y_HALF, Y_HALF - p[:, 1])
    return np.minimum(barrel, caps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--e", type=float, default=0.45)
    ap.add_argument("--mu", type=float, default=0.25)
    ap.add_argument("--dt", type=float, default=1e-4)
    ap.add_argument("--iters", type=int, nargs=2, default=[12, 8])
    ap.add_argument("--tend", type=float, default=5.0)
    ap.add_argument("--jacobi", action="store_true")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    d = np.loadtxt(IC, skiprows=1)
    radii, pos = d[:, 0].astype(np.float64), d[:, 1:4].astype(np.float64)
    n = len(d)
    is_m1 = radii < 0.0015
    rho = np.where(is_m1, 2500.0, 2000.0)
    print(f"N={n}  M1={int(is_m1.sum())}  M2={int((~is_m1).sum())}")

    sim = dem.Simulation(n)
    r0 = 0.001
    sim.set_sphere_shape(r0)
    lo = (-0.105, -0.036, -0.105)
    hi = (0.105, 0.036, 0.105)
    sim.set_domain(lo, hi)
    sim.enable_periodicity(False, False, False)
    wall = build_wall_sdf(drum_sdf, (lo, hi), resolution=(192, 72, 192))
    wid = wall.add_to(sim, restitution=0.4, friction=0.2)
    # wall surface moves +z at +x  <=>  omega_y = -2 rad/s about the drum centre
    sim.set_wall_velocity(wid, (0.0, 0.0, 0.0), (0.0, -OMEGA, 0.0), (0.0, 0.0, 0.0))
    # exact benchmark pair materials when supported: 0 = M1, 1 = M2, 2 = steel drum
    per_pair = hasattr(sim, "set_pair_material")
    if per_pair:
        sim.set_pair_material(0, 0, 0.5, 0.3)    # M1-M1
        sim.set_pair_material(0, 1, 0.45, 0.2)   # M1-M2
        sim.set_pair_material(1, 1, 0.4, 0.4)    # M2-M2
        sim.set_pair_material(0, 2, 0.4, 0.2)    # M1-steel
        sim.set_pair_material(1, 2, 0.4, 0.2)    # M2-steel
        sim.set_wall_material_id(wid, 2)

    sim.set_positions(pos.astype(np.float32))
    sim.set_scales((radii / r0).astype(np.float32))
    m = rho * 4.0 / 3.0 * np.pi * radii**3
    sim.set_inv_mass((1.0 / m).astype(np.float32))
    inv_I = (1.0 / (0.4 * m * radii**2)).astype(np.float32)
    sim.set_inv_inertia(np.repeat(inv_I[:, None], 3, axis=1).astype(np.float32))
    sim.set_velocities(np.zeros((n, 3), np.float32))
    if per_pair:
        sim.set_material_ids(np.where(is_m1, 0, 1).astype(np.int32).tolist())

    sim.set_gravity(0.0, 0.0, -9.81)
    sim.set_material_params(args.e, 0.0, args.mu)
    sim.set_solver_iterations(args.iters[0], args.iters[1])
    sim.set_thermostat(0.0, 0.0)
    if args.jacobi:
        sim.set_velocity_use_gs(False)

    nsteps = int(round(args.tend / args.dt))
    rec_every = max(1, int(round(0.1 / args.dt)))
    ts, z1_m1, z1_m2, z2_m1, z2_m2 = [], [], [], [], []
    com_m1, com_m2 = [], []

    mass1 = m[is_m1].sum()
    mass2 = m[~is_m1].sum()

    t0 = time.perf_counter()
    for i in range(nsteps + 1):
        if i % rec_every == 0:
            p = sim.get_positions()
            in1 = (p[:, 0] > 0) & (p[:, 2] > 0)
            in2 = (p[:, 0] < 0) & (p[:, 2] < 0)
            ts.append(i * args.dt)
            z1_m1.append(int((in1 & is_m1).sum()))
            z1_m2.append(int((in1 & ~is_m1).sum()))
            z2_m1.append(int((in2 & is_m1).sum()))
            z2_m2.append(int((in2 & ~is_m1).sum()))
            com_m1.append(p[is_m1].mean(axis=0))
            com_m2.append(p[~is_m1].mean(axis=0))
        if i < nsteps:
            sim.step(args.dt)
    wall_s = time.perf_counter() - t0

    out = args.out or f"case2_peclet{'_jac' if args.jacobi else ''}.npz"
    np.savez(out, t=np.array(ts), z1_m1=z1_m1, z1_m2=z1_m2, z2_m1=z2_m1, z2_m2=z2_m2,
             com_m1=np.array(com_m1), com_m2=np.array(com_m2), wall_s=wall_s,
             dt=args.dt, e=args.e, mu=args.mu)
    print(f"wall={wall_s:.0f}s  Zone2 M1 at end={z2_m1[-1]}")


if __name__ == "__main__":
    main()
