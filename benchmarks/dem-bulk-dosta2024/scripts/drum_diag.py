#!/usr/bin/env python
"""Drum kinematics diagnostic: WHERE does the impulse solver slip vs the Hertz engine?

Runs 2.0 s of the benchmark drum with either engine and records, every 0.1 s:
  - bed mean angular velocity about the drum axis, by radial band (r/R in 4 bands),
    normalized by the drum's omega ( = 1 means perfect co-rotation);
  - wall-layer slip: mean tangential surface-velocity difference grain-vs-wall for
    grains within 1.5 small-grain-diameters of the barrel;
  - the fraction of wall-layer grains whose contact slides (|slip| > 0.05 * wall speed).
"""
import argparse

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
    ap.add_argument("--engine", choices=["impulse", "hertz"], default="impulse")
    ap.add_argument("--iters", type=int, nargs=2, default=[12, 8])
    ap.add_argument("--dt", type=float, default=None)
    ap.add_argument("--tend", type=float, default=2.0)
    args = ap.parse_args()
    dt = args.dt or (8e-7 if args.engine == "hertz" else 1e-4)

    d = np.loadtxt(IC, skiprows=1)
    radii, pos = d[:, 0].astype(np.float64), d[:, 1:4].astype(np.float64)
    n = len(d)
    is_m1 = radii < 0.0015
    rho = np.where(is_m1, 2500.0, 2000.0)

    sim = dem.Simulation(n)
    sim.set_sphere_shape(0.001)
    lo, hi = (-0.105, -0.036, -0.105), (0.105, 0.036, 0.105)
    sim.set_domain(lo, hi)
    sim.enable_periodicity(False, False, False)
    wall = build_wall_sdf(drum_sdf, (lo, hi), resolution=(192, 72, 192))
    wid = wall.add_to(sim, restitution=0.4, friction=0.2)
    sim.set_wall_velocity(wid, (0, 0, 0), (0, -OMEGA, 0), (0, 0, 0))
    sim.set_pair_material(0, 0, 0.5, 0.3)
    sim.set_pair_material(0, 1, 0.45, 0.2)
    sim.set_pair_material(1, 1, 0.4, 0.4)
    sim.set_pair_material(0, 2, 0.4, 0.2)
    sim.set_pair_material(1, 2, 0.4, 0.2)
    sim.set_wall_material_id(wid, 2)
    sim.set_positions(pos.astype(np.float32))
    sim.set_scales((radii / 0.001).astype(np.float32))
    m = rho * 4 / 3 * np.pi * radii**3
    sim.set_inv_mass((1.0 / m).astype(np.float32))
    sim.set_inv_inertia(np.repeat((1.0 / (0.4 * m * radii**2))[:, None], 3, 1).astype(np.float32))
    sim.set_velocities(np.zeros((n, 3), np.float32))
    sim.set_material_ids(np.where(is_m1, 0, 1).astype(np.int32).tolist())
    sim.set_gravity(0, 0, -9.81)
    sim.set_material_params(0.45, 0.0, 0.25)
    sim.set_solver_iterations(args.iters[0], args.iters[1])
    sim.set_thermostat(0, 0)
    import os
    if os.environ.get("NOSTAB"):
        sim.set_stabilization(False)
    if args.engine == "hertz":
        sim.set_hertz_material(0, 1.0e9, 0.2)
        sim.set_hertz_material(1, 0.5e9, 0.2)
        sim.set_hertz_material(2, 210.0e9, 0.2)

    rec = 0.1
    nrec = int(round(args.tend / rec))
    per = int(round(rec / dt))
    print(f"# engine={args.engine} dt={dt:g} iters={args.iters}")
    print("# t | omega_bed/omega bands r/R<0.5,0.5-0.75,0.75-0.9,0.9-1 | "
          "wall-layer slip/(wR) | sliding frac")
    for k in range(nrec + 1):
        p = sim.get_positions()
        v = sim.get_velocities()
        w = sim.get_angular_velocities()
        r = np.sqrt(p[:, 0] ** 2 + p[:, 2] ** 2)
        # angular velocity of each grain about the axis: (r x v)_y / r^2 with axis y
        omg = (p[:, 2] * v[:, 0] - p[:, 0] * v[:, 2]) / np.maximum(r, 1e-6) ** 2
        # drum rotates with omega_y = -2 -> co-rotation means omg = -OMEGA; normalize
        co = omg / (-OMEGA)
        bands = [(0.0, 0.5), (0.5, 0.75), (0.75, 0.9), (0.9, 1.01)]
        vals = []
        for a, b in bands:
            sel = (r >= a * R_DRUM) & (r < b * R_DRUM)
            vals.append(co[sel].mean() if sel.sum() > 20 else np.nan)
        # wall layer: within 1.5 small diameters of the barrel
        wl = r > (R_DRUM - 3e-3)
        if wl.sum() > 20:
            # tangential unit vector for drum rotation (surface moves +z at +x): t = (z,0,-x)/r?
            # wall surface velocity: v_w = omega x r with omega=(0,-2,0): v_w = (-2)*(y x r)
            vwx = -OMEGA * p[wl, 2] * -1.0
            vwz = -OMEGA * -p[wl, 0] * -1.0
            # v_wall = omega x r ; omega=(0,-W,0), r=(x,0,z) -> v = (-W)*(y_hat x r) = (-W)*(z,0,-x)
            vwx = -OMEGA * p[wl, 2]
            vwz = OMEGA * p[wl, 0]
            # grain surface point velocity at the wall contact ~ v + w x (r_hat * a)
            rh = np.stack([p[wl, 0] / r[wl], np.zeros(wl.sum()), p[wl, 2] / r[wl]], 1)
            arm = rh * radii[wl][:, None]
            vs = v[wl] + np.cross(w[wl], arm)
            slip = np.stack([vs[:, 0] - vwx, vs[:, 2] - vwz], 1)
            # tangential projection (remove radial component)
            rad_comp = slip[:, 0] * rh[:, 0] + slip[:, 1] * rh[:, 2]
            slip_t = slip - rad_comp[:, None] * np.stack([rh[:, 0], rh[:, 2]], 1)
            smag = np.linalg.norm(slip_t, axis=1)
            wall_speed = OMEGA * r[wl]
            snorm = (smag / np.maximum(wall_speed, 1e-6))
            sfrac = float((snorm > 0.05).mean())
            smean = float(snorm.mean())
        else:
            smean, sfrac = np.nan, np.nan
        print("t=%.1f  co-rot: %s  wall-slip %.3f  sliding-frac %.2f" %
              (k * rec, " ".join("%.3f" % x for x in vals), smean, sfrac), flush=True)
        if k < nrec:
            if args.engine == "hertz":
                sim.step_hertz(dt, per)
            else:
                for _ in range(per):
                    sim.step(dt)


if __name__ == "__main__":
    main()
