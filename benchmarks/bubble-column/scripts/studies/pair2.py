#!/usr/bin/env python3
"""Drafting pair with film diagnostics.  PAIR_MODE=block (block container, run_peclet.build) or
struct (single-field VoF, same initial colour); PAIR_ABL (struct only) = none | mom (momentum-
consistent advection) | harm (harmonic face viscosity) | mhf (mixed height-position curvature fit,
TBFsolver's parabola-fit fallback).  Resolution: BUBBLE_COLUMN_CELLS_PER_D.
    python pair2.py --out DIR --t-end 30 --dt-out 0.05
"""
import json, math, os, sys, time
import numpy as np
from scipy import ndimage
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, SCRIPTS); sys.path.insert(0, HERE)
import case
from film import gap_markers, gap_single
LX, LY, LZ, SEP, DZ, X0 = 12.0, 6.0, 6.0, 2.0, float(os.environ.get("PAIR_DZ", "0.1")), 4.0
case.LX, case.LY, case.LZ = LX, LY, LZ
S = case.CELLS_PER_D
case.NX, case.NY, case.NZ = int(LX * S), int(LY * S), int(LZ * S)
case.NBX, case.NBY, case.NBZ = 2, 1, 1
case.NB = 2
case.bubble_centres = lambda: np.array([[X0, LY / 2, LZ / 2], [X0 + SEP, LY / 2, LZ / 2 + DZ]])
import run_peclet
import peclet.flow as pf
MODE = os.environ.get("PAIR_MODE", "block"); ABL = os.environ.get("PAIR_ABL", "none")
NX, NY, NZ = case.NX, case.NY, case.NZ
N = (NX, NY, NZ); L = (LX, LY, LZ)
OUT, T_END, DT_OUT, DTSAFE = run_peclet.OUT, run_peclet.T_END, run_peclet.DT_OUT, run_peclet.DTSAFE


def build_struct(C0):
    s = pf.Solver(NX, NY, NZ)
    s.set_rho(case.RHO_L)
    s.set_mu(S * S * case.MU_L)
    s.set_domain_bc("-y", "wall", (0, 0, 0))
    s.set_domain_bc("+y", "wall", (0, 0, 0))
    s.set_pressure_geometry(np.full((NX, NY, NZ), 10.0, order="F"))
    s.enable_vof()
    s.set_vof(np.asfortranarray(C0))
    s.set_property_model("rho", "linear", "C", [case.RHO_L, case.RHO_G - case.RHO_L])
    s.set_property_model("mu", "linear", "C", [S * S * case.MU_L, S * S * (case.MU_G - case.MU_L)])
    if ABL == "harm":
        s.diagnostics.set_property_mode("variable", True)
    s.set_surface_tension(S ** 3 * case.SIGMA)
    if ABL == "mhf":
        s.diagnostics.set_vof_curvature_mixed_height_fit(True)
    s.set_pressure_pcg(True, 800, 1e-10)
    alpha = float(C0.sum()) / (NX * NY * NZ)
    rho_av = case.RHO_L + (case.RHO_G - case.RHO_L) * alpha
    s.set_property_model("force_x", "linear", "C",
                         [S * (case.RHO_L - rho_av) * case.G, S * (case.RHO_G - case.RHO_L) * case.G])
    s.set_superficial_velocity(True, "x", 0.0)
    if ABL == "mom":
        s.enable_vof_momentum(case.RHO_G, case.RHO_L)
    return s


def components(C):
    lab, n = ndimage.label(C > 1e-3)
    parent = list(range(n + 1))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b in ((lab[0], lab[-1]), (lab[:, :, 0], lab[:, :, -1])):
        m = (a > 0) & (b > 0)
        for p, q in zip(a[m], b[m]):
            parent[find(p)] = find(q)
    lab = np.array([find(i) for i in range(n + 1)])[lab]
    out = []
    for r in np.unique(lab[lab > 0]):
        idx = np.nonzero(lab == r); w = C[idx]
        if w.sum() < 0.05 * S ** 3:
            continue
        cen = []
        for k in range(3):
            x = idx[k].astype(float); dx = x - x[0]
            if k != 1:
                dx -= N[k] * np.round(dx / N[k])
            cen.append((x[0] + (w * dx).sum() / w.sum() + 0.5) / S)
        out.append(cen)
    return out


def rec_block(s, t):
    st = sorted(s.diagnostics.vof_block_stats(), key=lambda b: b["id"])
    cen = [list(np.array(b["centroid"]) / S) for b in st]
    vel = [list(np.array(b["velocity"]) / S) for b in st]
    d = np.array(cen[1]) - np.array(cen[0]); d[0] -= LX * round(d[0] / LX); d[2] -= LZ * round(d[2] / LZ)
    gap = float("nan")
    if np.linalg.norm(d) < 1.5:
        a = [np.asarray(s.vof_block_color(b["id"])) for b in st]
        gap = float(gap_markers(a[0], st[0]["lo"], a[1], st[1]["lo"], cen[0], cen[1], S, N, L))
    return {"t": t, "cen3": cen, "vel3": vel, "gap": gap}


def rec_struct(s, t, prev):
    C = np.asarray(s.get_field("C"))
    cen = components(C)
    if len(cen) == 2 and prev is not None:   # keep identity: match to previous leading bubble
        dd = [np.linalg.norm(((np.array(c) - prev[0] + np.array(L) / 2) % np.array(L)) - np.array(L) / 2)
              for c in cen]
        if dd[1] < dd[0]:
            cen = cen[::-1]
    gap = float("nan")
    if len(cen) == 2:
        d = np.array(cen[1]) - np.array(cen[0]); d[0] -= LX * round(d[0] / LX); d[2] -= LZ * round(d[2] / LZ)
        if np.linalg.norm(d) < 1.5:
            gap = float(gap_single(C, cen[0], cen[1], S, N, L))
    return {"t": t, "cen3": cen, "gap": gap}


def main():
    os.makedirs(OUT, exist_ok=True)
    if MODE == "block":
        s = run_peclet.build()
        sample = lambda t, prev: rec_block(s, t)
    else:
        s0 = run_peclet.build(); C0 = np.array(s0.get_field("C")); del s0
        s = build_struct(C0)
        sample = lambda t, prev: rec_struct(s, t, prev)
    print(case.summary(), "mode", MODE, "abl", ABL, flush=True)
    t, step, series = 0.0, 0, []
    series.append(sample(0.0, None))
    next_out = DT_OUT; w0 = time.time()
    while t < T_END - 1e-12:
        Lm = s.vof_step_limits()
        for nm in ("cfl_dt", "capillary_dt"):
            if math.isnan(Lm[nm]) or not Lm[nm] > 0:
                raise SystemExit(f"step {step}: {nm} = {Lm[nm]}")
        dt = min(DTSAFE * Lm["cfl_dt"], DTSAFE * Lm["capillary_dt"], next_out - t)
        s.set_dt(dt); s.step(); t += dt; step += 1
        if t >= next_out - 1e-9:
            r = sample(t, np.array(series[-1]["cen3"]) if len(series[-1]["cen3"]) == 2 else None)
            series.append(r); next_out += DT_OUT
            if abs(t - round(t)) < 1e-6:
                print(f"  t {t:6.2f} step {step} dt {dt:.2e} gap {r['gap']:.4f} "
                      f"{1000*(time.time()-w0)/step:.0f} ms/step", flush=True)
                json.dump(series, open(os.path.join(OUT, "series.json"), "w"))
            if len(r["cen3"]) != 2:
                print(f"COALESCED at t {t:.3f}", flush=True); break
    json.dump(series, open(os.path.join(OUT, "series.json"), "w"))
    print(f"done: {step} steps, t = {t:.3f}")


main()
