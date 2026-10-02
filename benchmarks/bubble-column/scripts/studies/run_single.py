"""Loisy, Naso & Spelt (JFM 816, 2017) E1 free array with ONE structured VoF colour field (no
marker container): 8 bubbles, triply periodic 4.8 D box, 96^3 (D/h = 20), phi = 3.79 %.

  LOISY_RATIO=bt     rho_g/rho_l = mu_g/mu_l = 0.02 (Bunner & Tryggvason; = run_s1)       [A1]
  LOISY_RATIO=loisy  rho_g/rho_l = 1e-3, mu_g/mu_l = 1e-2 (Loisy table 1), with
                     enable_vof_momentum(rho_g, rho_l)                                        [A2]

Ar = 29.9 and Bo = 2 with (rho_l - rho_g) in both.  C is the LIQUID fraction (the structured
path's documented convention; the momentum-consistent advector reads C = 1 as rho_l).  Cell units
with physical time as run_peclet.py (S = cells per D).  Bubbles may coalesce numerically (one
field): every output counts the connected gas regions (periodic) and the min gap between them.

Usage: PYTHONPATH=<flow module> python run_single.py --out DIR [--t-end 100]   (resumes from DIR)
"""
import json, math, os, sys, time
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
import peclet.flow as pf

def arg(name, default, cast=float):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default

OUT = arg("--out", "run", str)
T_END = arg("--t-end", 100.0)
DTSAFE = arg("--dt-safety", 0.25)
DT_OUT = 1.0
RATIO = os.environ.get("LOISY_RATIO", "bt")
AR, BO, D, G, RHO_L = 29.9, 2.0, 1.0, 1.0, 1.0
RHO_G, MU_RATIO = (0.02, 0.02) if RATIO == "bt" else (1e-3, 1e-2)
MOM = int(os.environ.get("LOISY_MOM", "0" if RATIO == "bt" else "1")) == 1   # override: on/off test
MU_L = math.sqrt(RHO_L * (RHO_L - RHO_G) * G * D ** 3) / AR
MU_G = MU_RATIO * MU_L
SIGMA = (RHO_L - RHO_G) * G * D ** 2 / BO
U0 = 31.0 * MU_L / (RHO_L * D)                    # Loisy table 1: Re0 = 31 (Loth 2008)
L = 4.8
N = 96
S = N / L
NB = int(os.environ.get("LOISY_NB", "8"))   # 1 = the isolated-bubble control

def centres(seed=1):                              # = run_loisy.py (seed 1): same initial array
    rng = np.random.default_rng(seed)
    pts = []
    while len(pts) < NB:
        c = rng.random(3) * L
        if all(np.linalg.norm(np.minimum(np.abs(c - q), L - np.abs(c - q))) >= 1.6 for q in pts):
            pts.append(c)
    return np.array(pts)

def gas_fraction(cen, sub=6):
    """Exact-ish sphere volume fraction per cell by sub x sub x sub sampling (periodic images)."""
    g = np.zeros((N, N, N))
    o = (np.arange(sub) + 0.5) / sub
    R = 0.5 * D * S
    for c in cen * S:
        lo = np.floor(c - R).astype(int) - 1
        n = int(2 * R) + 3
        idx = [np.arange(lo[d], lo[d] + n) for d in range(3)]
        xs = [(idx[d][:, None] + o[None, :]).ravel() for d in range(3)]
        X, Y, Z = np.meshgrid(*xs, indexing="ij")
        inside = (X - c[0]) ** 2 + (Y - c[1]) ** 2 + (Z - c[2]) ** 2 <= R * R
        f = inside.reshape(n, sub, n, sub, n, sub).mean(axis=(1, 3, 5))
        I, J, K = np.meshgrid(*[i % N for i in idx], indexing="ij")
        np.add.at(g, (I, J, K), f)
    return np.minimum(g, 1.0)

def build():
    s = pf.Solver(N, N, N)
    s.set_rho(RHO_L)
    s.set_mu(S * S * MU_L)
    s.set_pressure_geometry(np.full((N, N, N), 10.0, order="F"))
    if MOM:
        s.enable_vof_momentum(RHO_G, RHO_L)       # calls enable_vof itself
    else:
        s.enable_vof()
    s.set_property_model("rho", "linear", "C", [RHO_G, RHO_L - RHO_G])
    s.set_property_model("mu", "linear", "C", [S * S * MU_G, S * S * (MU_L - MU_G)])
    s.set_surface_tension(S ** 3 * SIGMA)
    s.set_pressure_pcg(True, 800, 1e-10)
    return s

def set_buoyancy(s, C):
    """f_x = (rho(C) - <rho>) g along +x (= down), <rho> from the DISCRETE colour."""
    rho_av = RHO_G + (RHO_L - RHO_G) * float(C.mean())
    s.set_property_model("force_x", "linear", "C", [S * (RHO_G - rho_av) * G, S * (RHO_L - RHO_G) * G])

def regions(gas, thr):
    """Periodic connected components of gas > thr (face connectivity); returns labels, count."""
    lab, n = ndimage.label(gas > thr)
    parent = list(range(n + 1))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for ax in range(3):
        a = np.take(lab, 0, axis=ax).ravel(); b = np.take(lab, -1, axis=ax).ravel()
        for p, q in set(zip(a[(a > 0) & (b > 0)].tolist(), b[(a > 0) & (b > 0)].tolist())):
            rp, rq = find(p), find(q)
            if rp != rq: parent[rp] = rq
    roots = np.array([find(i) for i in range(n + 1)])
    lab = roots[lab]; lab[lab == roots[0]] = 0
    u = np.unique(lab[lab > 0])
    return lab, len(u), u

def min_gap(lab, ids):
    """Min periodic distance (D units) between cell centres of different gas regions, minus one
    cell: an estimate of the thinnest liquid film (0 = adjacent cells)."""
    if len(ids) < 2: return float("nan")
    border = lab > 0
    inner = border.copy()
    for ax in range(3):
        for sh in (-1, 1):
            inner &= np.roll(border, sh, axis=ax)
    border &= ~inner
    pts = {k: np.argwhere(border & (lab == k)) + 0.5 for k in ids}
    best = 1e30
    for i, a in enumerate(ids):
        t = cKDTree(pts[a], boxsize=N)
        for b in ids[i + 1:]:
            d, _ = t.query(pts[b], k=1)
            best = min(best, float(d.min()))
    return (best - 1.0) / S

def sample(s, t):
    C = s.get_field("C")
    gas = 1.0 - C
    u = s.get_u() / S
    uc = 0.5 * (u + np.roll(u, -1, axis=0))
    vg = float(gas.sum())
    ug = float((gas * uc).sum() / max(vg, 1e-30)); um = float(uc.mean())
    lab5, n5, ids5 = regions(gas, 0.5)
    _, n3, _ = regions(gas, 1e-3)
    vols = sorted((float(gas[lab5 == k].sum()) / S ** 3 for k in ids5), reverse=True)
    return {"t": t, "gas_volume": vg / S ** 3, "u_gas": ug, "u_mix": um, "drift": -(ug - um),
            "n_regions": n5, "n_regions_1e-3": n3, "min_gap": min_gap(lab5, list(ids5)),
            "region_vols": vols, "cmin": float(C.min()), "cmax": float(C.max())}

def save(path, s, step, t, series):
    tmp = path + ".tmp.npz"
    np.savez(tmp, step=np.int64(step), t=np.float64(t), C=s.get_field("C"), u=s.get_u(),
             v=s.get_v(), w=s.get_w(), p=s.get_field("p"), series=json.dumps(series))
    os.replace(tmp, path)

def main():
    os.makedirs(OUT, exist_ok=True)
    ck = os.path.join(OUT, "ckpt.npz")
    print(f"ratio {RATIO}: rho_g {RHO_G} mu_l {MU_L:.6f} mu_g {MU_G:.4e} sigma {SIGMA:.4f} "
          f"U0 {U0:.4f} momentum-consistent {MOM}", flush=True)
    s = build()
    if os.path.exists(ck):
        z = np.load(ck)
        step, t, series = int(z["step"]), float(z["t"]), json.loads(str(z["series"]))
        C = np.asfortranarray(z["C"])
        s.set_vof(C)
        for c, k in enumerate("uvw"):
            s.set_velocity(c, np.asfortranarray(z[k]))
        s.set_field("p", np.asfortranarray(z["p"]))
        s.diagnostics.set_vof_step_parity(step)
        set_buoyancy(s, np.load(os.path.join(OUT, "C0.npy")))
        print(f"resumed at step {step}, t = {t:.3f}", flush=True)
    else:
        C = np.asfortranarray(1.0 - gas_fraction(centres()))
        np.save(os.path.join(OUT, "C0.npy"), C)
        s.set_vof(C)
        set_buoyancy(s, C)
        step, t, series = 0, 0.0, []
        series.append(sample(s, 0.0))
        print(f"  t 0: {series[0]['n_regions']} regions, min gap {series[0]['min_gap']:.3f} D, "
              f"gas volume {series[0]['gas_volume']:.5f} (8 pi/6 = {8*math.pi/6:.5f})", flush=True)
    V0 = series[0]["gas_volume"]
    s.set_superficial_velocity(True, "x", 0.0)
    next_out = (math.floor(t / DT_OUT + 1e-9) + 1) * DT_OUT
    wall0 = time.time(); nstep = 0
    while t < T_END - 1e-12:
        Lm = s.vof_step_limits()
        for nm in ("cfl_dt", "capillary_dt"):
            if math.isnan(Lm[nm]) or not Lm[nm] > 0:
                raise SystemExit(f"step {step}: {nm} = {Lm[nm]} — state broken")
        dt = min(DTSAFE * Lm["cfl_dt"], DTSAFE * Lm["capillary_dt"], next_out - t)
        s.set_dt(dt); s.step()
        t += dt; step += 1; nstep += 1
        if t >= next_out - 1e-9:
            r = sample(s, t); series.append(r)
            print(f"  t {t:7.2f} step {step:6d} drift {r['drift']:.4f} regions {r['n_regions']}/"
                  f"{r['n_regions_1e-3']} gap {r['min_gap']:.3f} dV {r['gas_volume']/V0-1:+.1e} "
                  f"C[{r['cmin']:.1e},{r['cmax']-1:+.1e}] {1000*(time.time()-wall0)/nstep:.0f} ms/step",
                  flush=True)
            next_out += DT_OUT
            save(ck, s, step, t, series)
    save(ck, s, step, t, series)
    with open(os.path.join(OUT, "series.json"), "w") as f:
        json.dump(series, f)
    print(f"done: {step} steps, t = {t:.3f}, wall {time.time()-wall0:.0f} s", flush=True)

if __name__ == "__main__":
    main()
