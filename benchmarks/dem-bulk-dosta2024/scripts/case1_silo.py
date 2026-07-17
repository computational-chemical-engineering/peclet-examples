#!/usr/bin/env python
"""Dosta et al. 2024 benchmark — Case 1: silo emptying.

Cylindrical steel silo (R = 0.1 m) with a conical hopper; 100k particles (d = 4 mm) of
material M1 or M2 discharge through a 0.04 / 0.06 m orifice for 5 s. Initial packing =
the benchmark's shared InitialCoordinates. Output: number of particles remaining above
the orifice plane every 0.1 s (the paper's Fig. 7), plus the velocity snapshot at t = 2 s
(Fig. 6). Particles a bit below the orifice are deleted, as in the reference codes
(implemented as a periodic re-upload of the surviving state).

Geometry read off the benchmark wall meshes:
  large orifice: lip z0 = -0.0554222, r_orif = 0.03, cone height 0.07, top z = 0.3146
  small orifice: lip z0 = -0.0593008, r_orif = 0.02, cone height 0.08, top z = 0.3207
"""
import argparse
import os
import time

import numpy as np

from peclet import dem
from peclet.dem import build_wall_sdf

IC_DIR = os.environ.get("DOSTA_IC") or (
    "/tmp/claude-1003/-home-frankp-Codes-suite/9e9b807a-7a8a-4948-a080-545a0f831797/"
    "scratchpad/dosta2024/SupplementaryMaterial/InitialCoordinates/Case 1 - SiloFlow"
)

R_SILO = 0.1
R_PART = 0.002
GEOM = {
    "large": dict(z0=-0.0554222, r_orif=0.03, cone_h=0.07, ztop=0.314578),
    "small": dict(z0=-0.0593008, r_orif=0.02, cone_h=0.08, ztop=0.320699),
}
MAT = {  # grain-grain (e, mu), density; wall (steel) is (0.4, 0.2) for both
    "M1": dict(e=0.5, mu=0.3, rho=2500.0),
    "M2": dict(e=0.4, mu=0.4, rho=2000.0),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orifice", choices=["large", "small"], default="large")
    ap.add_argument("--mat", choices=["M1", "M2"], default="M1")
    ap.add_argument("--dt", type=float, default=2e-4)
    ap.add_argument("--iters", type=int, nargs=2, default=[12, 8])
    ap.add_argument("--tend", type=float, default=5.0)
    ap.add_argument("--jacobi", action="store_true")
    ap.add_argument("--mu", type=float, default=None,
                    help="override grain-grain friction (diagnostic)")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    g = GEOM[args.orifice]
    z0, r_orif, cone_h, ztop = g["z0"], g["r_orif"], g["cone_h"], g["ztop"]
    slope = (R_SILO - r_orif) / cone_h
    z_del = z0 - 0.03           # deletion line, a bit below the orifice
    z_grid_lo = z0 - 0.075      # wall grid must extend below the deletion line

    def silo_sdf(p):
        """Positive in the void. Inner surface r_inner(z): cone from the lip to the barrel,
        barrel above; below the lip a diverging phantom spout that the free jet never touches
        (keeps the trilinear SDF continuous across the orifice plane)."""
        r = np.sqrt(p[:, 0] ** 2 + p[:, 1] ** 2)
        z = p[:, 2]
        r_inner = np.where(
            z >= z0,
            np.minimum(R_SILO, r_orif + slope * (z - z0)),
            r_orif + 0.8 * (z0 - z),
        )
        return r_inner - r

    m = MAT[args.mat]
    pos = np.loadtxt(f"{IC_DIR}/PartCoordinates {args.mat} ({args.orifice} orifice).txt")
    n0 = len(pos)

    sim = dem.Simulation(n0)
    sim.set_sphere_shape(R_PART)
    lo = (-0.105, -0.105, z_grid_lo)
    hi = (0.105, 0.105, ztop + 0.01)
    sim.set_domain(lo, hi)
    sim.enable_periodicity(False, False, False)
    wall = build_wall_sdf(silo_sdf, (lo, hi), resolution=(128, 128, 256))
    wall.add_to(sim, restitution=0.4, friction=0.2)

    mass = m["rho"] * 4.0 / 3.0 * np.pi * R_PART**3
    inv_m = np.full(n0, 1.0 / mass, np.float32)
    inv_I = np.full((n0, 3), 1.0 / (0.4 * mass * R_PART**2), np.float32)

    sim.set_positions(pos.astype(np.float32))
    sim.set_scales_uniform(1.0)
    sim.set_inv_mass(inv_m)
    sim.set_inv_inertia(inv_I)
    sim.set_velocities(np.zeros((n0, 3), np.float32))
    sim.set_gravity(0.0, 0.0, -9.81)
    sim.set_material_params(m["e"], 0.0, args.mu if args.mu is not None else m["mu"])
    sim.set_solver_iterations(args.iters[0], args.iters[1])
    sim.set_thermostat(0.0, 0.0)
    if args.jacobi:
        sim.set_velocity_use_gs(False)

    nsteps = int(round(args.tend / args.dt))
    rec_every = max(1, int(round(0.1 / args.dt)))     # count every 0.1 s
    del_every = max(1, int(round(0.01 / args.dt)))    # delete every 0.01 s
    ts, counts = [], []
    vel_snapshot = None

    t0 = time.perf_counter()
    for i in range(nsteps + 1):
        t = i * args.dt
        if i % del_every == 0 or i % rec_every == 0:
            p = sim.get_positions()
            n = p.shape[0]
            if i % rec_every == 0:
                ts.append(t)
                counts.append(int((p[:, 2] > z0).sum()))
            if abs(t - 2.0) < 0.5 * args.dt and vel_snapshot is None:
                v = sim.get_velocities()
                keep = p[:, 2] > z0
                vel_snapshot = np.hstack([p[keep], v[keep]])
            if i % del_every == 0:
                alive = p[:, 2] > z_del
                nkeep = int(alive.sum())
                if nkeep < n:
                    # set_positions resets every per-particle array -> gather first,
                    # then re-upload the surviving rows
                    v = sim.get_velocities()
                    av = sim.get_angular_velocities()
                    sim.set_positions(np.ascontiguousarray(p[alive]))
                    sim.set_scales_uniform(1.0)
                    sim.set_inv_mass(np.ascontiguousarray(inv_m[:nkeep]))
                    sim.set_inv_inertia(np.ascontiguousarray(inv_I[:nkeep]))
                    sim.set_velocities(np.ascontiguousarray(v[alive]))
                    sim.set_angular_velocities(np.ascontiguousarray(av[alive]))
        if i < nsteps:
            sim.step(args.dt)
    wall_s = time.perf_counter() - t0

    out = args.out or (f"case1_{args.orifice}_{args.mat}_peclet"
                       f"{'_jac' if args.jacobi else ''}.npz")
    np.savez(out, t=np.array(ts), count=np.array(counts), wall_s=wall_s, dt=args.dt,
             iters=args.iters, vel_snapshot=vel_snapshot)
    print(f"{args.orifice}/{args.mat}: wall={wall_s:.0f}s  "
          f"N(2s)={np.interp(2.0, ts, counts):.0f}  N(end)={counts[-1]}")


if __name__ == "__main__":
    main()
