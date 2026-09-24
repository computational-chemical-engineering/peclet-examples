#!/usr/bin/env python3
"""peclet side of the bubble-column benchmark: the multiple-marker (block) VoF container.

Every bubble is its own marker (one Weymouth-Yue colour field on a moving box), so bubbles that
touch do not coalesce numerically; the union colour drives rho(C), mu(C) and the buoyancy
closure f_x = (rho(C) - <rho>) g, and each marker's own balanced-force CSF is summed into the
momentum right-hand side.  The case numbers come from case.py (shared with the TBFsolver run).

UNITS.  Like the other VoF pages the solver runs in CELL units with physical time: lengths are
scaled by S = cells per D, so velocity x S, mu x S^2, sigma x S^3, a force per volume x S, and
densities and times are unchanged.  Every output is converted back to D = rho_l = g = 1 units.

Usage:  PYTHONPATH=<flow build> python run_peclet.py --out run/ [--t-end 60] [--wall 36000]
Re-running the same command resumes from run/ckpt.npz.
"""
import json
import math
import os
import sys
import time

import numpy as np

import peclet.flow as pf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case  # noqa: E402


def arg(name, default, cast=float):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


OUT = arg("--out", "run", str)
T_END = arg("--t-end", case.T_END)
WALL = arg("--wall", 1e18)
DTSAFE = arg("--dt-safety", 0.25)
DT_OUT = arg("--dt-out", case.DT_OUT)
PRINT_EVERY = arg("--print-every", 100, int)
S = case.CELLS_PER_D
NX, NY, NZ = case.NX, case.NY, case.NZ


def build(blocks=None):
    s = pf.Solver(NX, NY, NZ)
    s.set_rho(case.RHO_L)
    s.set_mu(S * S * case.MU_L)
    s.set_domain_bc("-y", "wall", (0, 0, 0))
    s.set_domain_bc("+y", "wall", (0, 0, 0))
    s.set_pressure_geometry(np.full((NX, NY, NZ), 10.0, order="F"))
    s.enable_vof()
    s.set_vof(np.zeros((NX, NY, NZ), order="F"))
    # C = 1 is GAS (the block container's union starts empty, so a cell no marker covers is 0)
    s.set_property_model("rho", "linear", "C", [case.RHO_L, case.RHO_G - case.RHO_L])
    s.set_property_model("mu", "linear", "C", [S * S * case.MU_L, S * S * (case.MU_G - case.MU_L)])
    s.set_surface_tension(S ** 3 * case.SIGMA)
    s.set_pressure_chebyshev(True, 800, 1e-10)       # last: the rho closure re-selects the driver
    if blocks is None:
        seeds = [(c[0] * S, c[1] * S, c[2] * S, case.R * S) for c in case.bubble_centres()]
        s.enable_vof_blocks(seeds)
    else:
        s.enable_vof_blocks_from_colors([b for b, _ in blocks], [c for _, c in blocks])
    s.enable_vof_block_csf()
    # buoyancy with the mixture weight removed: f_x = (rho(C) - <rho>) g, + x = "down".  <rho> from
    # the DISCRETE gas volume (the markers' own, exactly conserved), not the analytic spheres: a
    # residual net force would accelerate the whole column until the wall friction balanced it
    # (TBFsolver's flowCtrl 3 recomputes <rho> from its field every step for the same reason).
    alpha = sum(b["volume"] for b in s.diagnostics.vof_block_stats()) / (NX * NY * NZ)
    rho_av = case.RHO_L + (case.RHO_G - case.RHO_L) * alpha
    s.set_property_model("force_x", "linear", "C",
                         [S * (case.RHO_L - rho_av) * case.G, S * (case.RHO_G - case.RHO_L) * case.G])
    return s


def block_state(s):
    out = []
    for b in s.diagnostics.vof_block_stats():
        lo, hi = b["lo"], b["hi"]
        out.append(([lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]],
                    np.asfortranarray(s.vof_block_color(b["id"]))))
    return out


def save_ckpt(path, s, step, t, series):
    d = {"step": np.int64(step), "t": np.float64(t), "u": s.get_u(), "v": s.get_v(),
         "w": s.get_w(), "p": s.get_field("p"), "series": json.dumps(series)}
    blocks = block_state(s)
    d["nblocks"] = np.int64(len(blocks))
    for i, (box, col) in enumerate(blocks):
        d[f"box{i}"] = np.asarray(box, dtype=np.int64)
        d[f"col{i}"] = np.asarray(col)
    tmp = path + ".tmp.npz"
    np.savez(tmp, **d)
    os.replace(tmp, path)


def load_ckpt(path):
    z = np.load(path)
    nb = int(z["nblocks"])
    blocks = [(np.array(z[f"box{i}"]).tolist(), np.asfortranarray(z[f"col{i}"])) for i in range(nb)]
    return (int(z["step"]), float(z["t"]), blocks,
            [np.asfortranarray(z[k]) for k in ("u", "v", "w")], np.asfortranarray(z["p"]),
            json.loads(str(z["series"])))


def sample(s, t):
    """One record in D = rho_l = g = 1 units."""
    st = s.diagnostics.vof_block_stats()
    C = s.get_field("C")
    u = s.get_u() / S                                  # x face velocity -> physical
    uc = 0.5 * (u + np.roll(u, -1, axis=0))            # cell centre (x periodic)
    vol_g = float(C.sum())
    ug = float((C * uc).sum() / max(vol_g, 1e-30))     # gas-phase mean x velocity
    um = float(uc.mean())                              # mixture volumetric mean
    ul = float(((1 - C) * uc).sum() / max((1 - C).sum(), 1e-30))
    alpha_y = C.mean(axis=(0, 2))
    ul_y = ((1 - C) * uc).sum(axis=(0, 2)) / np.maximum((1 - C).sum(axis=(0, 2)), 1e-30)
    vb = np.array([b["velocity"] for b in st]) / S     # per-marker centroid velocity
    vols = np.array([b["volume"] for b in st]) / S ** 3
    cen = np.array([b["centroid"] for b in st]) / S
    return {"t": t, "gas_volume": vol_g / S ** 3, "u_gas": ug, "u_mix": um, "u_liq": ul,
            "drift": -(ug - um),                       # rise speed, positive = towards -x (up)
            "bubble_ux": vb[:, 0].tolist(), "bubble_vol": vols.tolist(),
            "bubble_y": cen[:, 1].tolist(), "bubble_x": cen[:, 0].tolist(),
            "alpha_y": alpha_y.tolist(), "ul_y": ul_y.tolist(),
            "area": sum(b["area"] for b in st) / S ** 2}


def main():
    os.makedirs(OUT, exist_ok=True)
    ck = os.path.join(OUT, "ckpt.npz")
    print(case.summary())
    if os.path.exists(ck):
        step, t, blocks, vel, pres, series = load_ckpt(ck)
        s = build(blocks)
        for c, a in enumerate(vel):
            s.set_velocity(c, a)
        s.set_field("p", pres)
        s.diagnostics.set_vof_step_parity(step)
        print(f"resumed at step {step}, t = {t:.3f}")
    else:
        s = build()
        step, t, series = 0, 0.0, [sample(s, 0.0)]
    vol0 = np.array(series[0]["bubble_vol"])
    next_out = (math.floor(t / DT_OUT + 1e-9) + 1) * DT_OUT
    wall0 = time.time()
    nstep = 0
    while t < T_END - 1e-12:
        L = s.vof_step_limits()
        for nm in ("cfl_dt", "capillary_dt"):
            if math.isnan(L[nm]) or not L[nm] > 0:    # inf is fine (fluid at rest)
                raise SystemExit(f"step {step}: {nm} = {L[nm]} — state broken; last checkpoint kept")
        dt = min(DTSAFE * L["cfl_dt"], DTSAFE * L["capillary_dt"], next_out - t)
        s.set_dt(dt)
        s.step()
        # CLOSED column: zero net volume flux, the batch-column condition (TBFsolver flowCtrl 2,
        # flow_rate 0).  A uniform shift of every x-face velocity keeps the field discretely
        # divergence-free (x is periodic, the walls are y faces) and removes the net upflow that
        # wall friction on the down-flowing liquid would otherwise build up.
        u = s.get_u()
        ub = float(u.mean())
        s.set_velocity(0, np.asfortranarray(u - ub))
        t += dt
        step += 1
        nstep += 1
        if step % PRINT_EVERY == 0:
            um = max(np.abs(s.get_u()).max(), np.abs(s.get_v()).max(), np.abs(s.get_w()).max()) / S
            print(f"  step {step:7d} t {t:8.3f} dt {dt:.2e} max|u| {um:.3f} press "
                  f"{s.diagnostics.last_pressure_iterations():3d}  "
                  f"{1000*(time.time()-wall0)/nstep:.0f} ms/step", flush=True)
        if t >= next_out - 1e-9:
            rec = sample(s, t)
            series.append(rec)
            dv = np.abs(np.array(rec["bubble_vol"]) / vol0 - 1).max()
            print(f"  t {t:7.2f}  drift {rec['drift']:.4f}  u_mix {rec['u_mix']:+.2e}  "
                  f"marker dV {dv:.1e}", flush=True)
            next_out += DT_OUT
            save_ckpt(ck, s, step, t, series)
            if time.time() - wall0 > WALL:
                print("wall budget reached; checkpoint written")
                return
    save_ckpt(ck, s, step, t, series)
    with open(os.path.join(OUT, "series.json"), "w") as f:
        json.dump(series, f)
    print(f"done: {step} steps, t = {t:.3f}")


if __name__ == "__main__":
    main()
