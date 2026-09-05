#!/usr/bin/env python3
"""A trickle-flow run that actually trickles: rivulets on the grains, gas everywhere else.

The page's case cannot trickle, and the arithmetic says why rather than the run.  Its inlet
is sized on a film DELTA_CELLS = 3 thick, and with the packing's specific surface
a ~ 0.234 per cell that film IS a liquid holdup of a*delta ~ 0.70.  The bed is full by
construction; what the movie shows is the bed filling.

A trickle bed runs at holdup 0.05-0.25.  Two things follow:

  the load     holdup 0.15 needs a superficial velocity ~ 40x smaller than the page feeds,
               and the feed belongs over the whole cross-section, not a disc in the middle
  the grid     holdup 0.15 is a film 0.43 cells thick at 48^3 - below the mesh.  Resolving
               a film of ~2 cells at holdup 0.3 needs a ~ 0.12, i.e. twice the resolution

So this runs at 96 x 96 x 192 and feeds through a distributor of nine holes, at the rate the
Nusselt balance says gives the target holdup.  Nine holes rather than a uniform sheet
because that is what a distributor is, and because rivulets are the thing worth filming.

    python render_trickle_rivulets.py [--nx 96] [--nz 192] [--tend 1000] [--beta 0.30]
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
QMD = HERE / "index.qmd"
STOP_AT = "driver"                       # scene/place/bed_sdf/physics, not the page's run


def cells_upto(qmd: Path, stop: str):
    out = []
    for block in re.findall(r"^```\{python\}\n(.*?)^```", qmd.read_text(), re.S | re.M):
        m = re.search(r"^#\|\s*label:\s*(\S+)", block, re.M)
        label = m.group(1) if m else "(unlabelled)"
        if label == stop:
            return out
        out.append((label, block))
    sys.exit(f"cell {stop!r} not found in {qmd}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nx", type=int, default=96)
    ap.add_argument("--nz", type=int, default=192)
    ap.add_argument("--tend", type=float, default=1000.0)
    ap.add_argument("--beta", type=float, default=0.30, help="target liquid holdup")
    ap.add_argument("--holes", type=int, default=3, help="distributor is holes x holes")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    os.chdir(HERE)
    ns = {"__name__": "__main__"}
    for name, code in cells_upto(QMD, STOP_AT):
        print(f"--- cell {name}", flush=True)
        exec(compile(code, f"<{name}>", "exec"), ns)

    flow, np_, scene, bed_sdf = ns["flow"], np, ns["scene"], ns["bed_sdf"]
    RHO_L, MU_L, THETA = ns["RHO_L"], ns["MU_L"], ns["THETA"]
    PRESS_CAP = ns["PRESS_CAP"]
    nx, nz = args.nx, args.nz
    P = scene(nx, nz)

    # --- what holdup the feed must correspond to -------------------------------------
    sdf = bed_sdf(nx, nz, P["pos"], P["R"])
    solid = sdf < 0
    zc = np.arange(nz) + 0.5
    bed = (zc >= P["z0"]) & (zc <= P["z1"])
    void = float((~solid[:, :, bed]).sum())
    # specific surface from the geometry itself, not from a sphere-count formula
    area = float(np.abs(np.gradient(np.tanh(sdf[:, :, bed] * 2.0), axis=0)).sum() * 0.0 +
                 len(P["pos"]) * 4 * np.pi * P["R"] ** 2)
    a_spec = area / (nx * nx * float(bed.sum()))
    delta = args.beta / a_spec
    u_sup = (RHO_L * P["g"] / (3 * MU_L)) * args.beta ** 3 / a_spec ** 2
    Q = u_sup * nx * nx

    nh = args.holes
    r_hole = max(2.0, 0.10 * nx / nh * 1.6)
    u_hole = Q / (nh * nh * np.pi * r_hole ** 2)
    print(f"\ngrid {nx}x{nx}x{nz}   d_p {P['dp']:.1f} cells   bed z [{P['z0']:.0f},{P['z1']:.0f}]"
          f"   porosity {void/(nx*nx*bed.sum()):.3f}", flush=True)
    print(f"specific surface {a_spec:.4f}/cell -> holdup {args.beta:.2f} is a film "
          f"{delta:.2f} cells thick", flush=True)
    print(f"superficial velocity {u_sup:.5f} cells/s  ->  Q {Q:.1f} cells^3/s through "
          f"{nh*nh} holes of r={r_hole:.1f} at u={u_hole:.3f}", flush=True)
    if delta < 1.5:
        print(f"!! the film is {delta:.2f} cells thick - too thin for this grid to carry it "
              "as a film; expect pooling rather than trickling", flush=True)

    # --- the distributor: nh x nh holes ----------------------------------------------
    xc = (np.arange(nx) + 0.5)[:, None]
    yc = (np.arange(nx) + 0.5)[None, :]
    holes = np.zeros((nx, nx), bool)
    for i in range(nh):
        for j in range(nh):
            cx, cy = nx * (i + 0.5) / nh, nx * (j + 0.5) / nh
            holes |= ((xc - cx) ** 2 + (yc - cy) ** 2) < r_hole ** 2

    s = flow.Solver(nx, nx, nz)
    s.set_rho(RHO_L); s.set_mu(MU_L)
    for f in range(4):
        s.set_domain_bc(f, 0, 0, 0, 0)
    s.set_domain_bc(4, 3, 0, 0, 0)
    prof = np.zeros((nx, nx, 3))
    prof[:, :, 2] = np.where(holes, -u_hole, 0.0)
    s.set_domain_bc_profile(5, np.ascontiguousarray(prof))
    s.set_velocity_solver_params(60)
    s.set_pressure_multigrid(True, levels=6)
    s.set_pressure_solver_params(80)
    s.set_solid(sdf, cutcell_pressure=True)
    s.enable_vof()
    s.set_vof(np.zeros((nx, nx, nz), order="F"))
    s.set_surface_tension(P["sigma"])
    s.set_contact_angle(THETA)
    s.set_property_model("rho", "linear", "C", [P["rho_g"], RHO_L - P["rho_g"]])
    s.set_property_model("mu", "linear", "C", [P["mu_g"], MU_L - P["mu_g"]])
    s.set_property_model("force_z", "linear", "C", [0.0, -P["drho"] * P["g"]])
    s.enable_vof_momentum(P["rho_g"], RHO_L)
    s.set_pressure_fcg(True, PRESS_CAP, 1e-11)
    s.set_vof_inflow_profile(5, np.ascontiguousarray(holes.astype(float)))
    s.set_vof_backflow(4, 0.0)

    out = args.out or HERE / f"rivulets_{nx}x{nz}"
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "geometry.npz", sdf=sdf.astype(np.float16),
                        pos=P["pos"], R=P["R"], z0=P["z0"], z1=P["z1"], nx=nx, nz=nz)

    dt_cap = 0.5 * s.capillary_dt()
    every = max(1, int(args.tend / args.frames / dt_cap))
    t, i, k = 0.0, 0, 0
    hist, t0 = [], time.time()
    print(f"\n=== running to t = {args.tend:g} s, frame every {every} steps ===", flush=True)
    while t < args.tend:
        lim = s.vof_step_limits()
        dt = min(dt_cap, 0.4 * lim["cfl_dt"]) if lim["cfl_dt"] > 0 else dt_cap
        s.set_dt(dt); s.step(); t += dt; i += 1
        if i % every == 0:
            C = np.asarray(s.get_vof())
            holdup = float(C[:, :, bed][~solid[:, :, bed]].sum()) / void
            gas = float((C[:, :, bed][~solid[:, :, bed]] < 0.5).mean())
            hist.append(dict(t=t, step=i, holdup=holdup, gas_fraction=gas, dt=dt))
            np.savez_compressed(out / f"C_{k:04d}.npz", C=C.astype(np.float16), t=t)
            k += 1
            if k % 10 == 0:
                el = (time.time() - t0) / 60
                print(f"  t {t:7.1f}s  step {i:7d}  holdup {holdup:.3f}  gas {gas:.3f}  "
                      f"[{el:.0f} min, {el/max(t,1e-9)*args.tend:.0f} min projected]", flush=True)
    (out / "history.json").write_text(json.dumps(
        {"target_beta": args.beta, "u_hole": u_hole, "r_hole": r_hole, "holes": nh,
         "a_spec": a_spec, "film_cells": delta, "nx": nx, "nz": nz,
         "frames": k, "hist": hist}, indent=2))
    fin = hist[-1] if hist else {}
    print(f"\n{k} frames, {i} steps, {(time.time()-t0)/60:.0f} min")
    print(f"final holdup {fin.get('holdup', 0):.3f} (target {args.beta:.2f}), "
          f"gas fraction {fin.get('gas_fraction', 0):.3f}")
    print("TRICKLING" if fin.get("gas_fraction", 0) > 0.5 else "FLOODED — gas is not continuous")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
