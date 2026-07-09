#!/usr/bin/env python
"""Turbulent plane-channel DNS on the peclet `flow` solver, benchmarked vs MKM 1999.

Grid units: dx=dy=dz=1 (solver is isotropic unit-spacing, no wall-normal stretching).
Choose u_tau = 1  ->  every velocity comes out directly in wall units (u+ = u),
and y+ = y / nu.  Constant-pressure-gradient (CPG) forcing f = 2/ny pins u_tau = 1
exactly by global momentum balance (tau_w = f*H, H = ny/2).

  Re_tau = u_tau H / nu = 180  =>  nu = (ny/2)/180 ,  Delta+ = 1/nu = 360/ny.

Env params: NX NY NZ NSTEPS DT DIAG STATSTART ADV(0=SOU,1=Koren) OUT SEED RESTART
"""
import os, sys, time
import numpy as np

NX = int(os.environ.get("NX", 384))
NY = int(os.environ.get("NY", 128))
NZ = int(os.environ.get("NZ", 128))
NSTEPS = int(os.environ.get("NSTEPS", 6000))
DT = float(os.environ.get("DT", 0.012))
DIAG = int(os.environ.get("DIAG", 100))
STATSTART = int(os.environ.get("STATSTART", 10**9))  # step to begin accumulating profile stats
ADV = int(os.environ.get("ADV", 0))                   # 0 = SOU (least dissipative), 1 = Koren-TVD
OUT = os.environ.get("OUT", "smoke")
SEED = int(os.environ.get("SEED", 12345))
RESTART = os.environ.get("RESTART", "")               # optional .npz with u,v,w to resume
CFR = float(os.environ.get("CFR", 0.0))               # >0: constant-flow-rate, hold bulk U+ at this target

RE_TAU = 180.0
nu = (NY / 2.0) / RE_TAU          # kinematic visc (rho=1 so mu=nu)
H = NY / 2.0                      # half-height (grid units)
fbody = 2.0 / NY                  # body force -> u_tau = sqrt(f*H) = 1
Dplus = 1.0 / nu                  # grid spacing in wall units

print(f"[cfg] grid {NX}x{NY}x{NZ}  nu={nu:.5f}  f={fbody:.6g}  H={H:.1f}  "
      f"Delta+={Dplus:.3f}  Lx+={NX*Dplus:.0f} Ly+={NY*Dplus:.0f} Lz+={NZ*Dplus:.0f}  "
      f"cells={NX*NY*NZ/1e6:.2f}M  dt={DT}  adv={'SOU' if ADV==0 else 'Koren'}", flush=True)

from peclet import flow

# ---- initial condition -----------------------------------------------------
yc = (np.arange(NY) + 0.5)                     # cell-center y (grid units)
dwall = np.minimum(yc, NY - yc)                # distance to nearest wall
yp = dwall / nu                                # y+ using nearest-wall distance (symmetric)

def reichardt(yplus):
    kap = 0.41
    return (1.0/kap)*np.log1p(kap*yplus) + 7.8*(1.0 - np.exp(-yplus/11.0)
            - (yplus/11.0)*np.exp(-0.33*yplus))

def lowpass_noise(shape, cutoff, rng):
    """White noise low-passed (keep |k|<cutoff in cycles/cell) -> smooth large scales."""
    g = rng.standard_normal(shape)
    G = np.fft.rfftn(g, axes=(0, 1, 2))
    kx = np.fft.fftfreq(shape[0])[:, None, None]
    ky = np.fft.fftfreq(shape[1])[None, :, None]
    kz = np.fft.rfftfreq(shape[2])[None, None, :]
    kmag = np.sqrt(kx*kx + ky*ky + kz*kz)
    G[kmag > cutoff] = 0.0
    out = np.fft.irfftn(G, s=shape, axes=(0, 1, 2))
    return out / (out.std() + 1e-12)

if RESTART and os.path.exists(RESTART):
    d = np.load(RESTART)
    u0, v0, w0 = d["u"], d["v"], d["w"]
    print(f"[ic] resumed from {RESTART}", flush=True)
else:
    rng = np.random.default_rng(SEED)
    Umean = reichardt(yp)                        # symmetric turbulent mean, 0 at walls
    env = (dwall/nu/15.0) * np.exp(1.0 - dwall/nu/15.0)  # near-wall amplitude env (peak y+~15)
    env = env[None, :, None]
    cut = 0.06
    u0 = Umean[None, :, None] + 2.6*env*lowpass_noise((NX, NY, NZ), cut, rng)
    v0 = 1.1*env*lowpass_noise((NX, NY, NZ), cut, rng)
    w0 = 1.5*env*lowpass_noise((NX, NY, NZ), cut, rng)
    print(f"[ic] Reichardt + near-wall low-pass noise; "
          f"u_rms~{u0.std():.2f} Umax~{u0.mean(axis=(0,2)).max():.1f}", flush=True)

u0 = np.asfortranarray(u0); v0 = np.asfortranarray(v0); w0 = np.asfortranarray(w0)

# ---- solver setup ----------------------------------------------------------
s = flow.Solver(NX, NY, NZ)
s.set_rho(1.0); s.set_mu(nu); s.set_dt(DT)
s.set_advection(True); s.set_advection_scheme(ADV)
s.set_velocity_solver_params(20)                 # implicit diffusion (small diff number)
s.set_pressure_multigrid(True, 5)
s.set_pressure_pcg(True, 80, 1e-4); s.set_pressure_warmstart(True)
s.set_domain_bc(2, 1); s.set_domain_bc(3, 1)     # no-slip walls on -y,+y ; x,z periodic (default)
s.set_body_force(0.0 if CFR > 0 else fbody, 0.0, 0.0)  # CPG body force, or 0 under CFR
s.set_pressure_geometry(np.asfortranarray(np.full((NX, NY, NZ), 1e30)))  # all-fluid
s.set_state(u0, v0, w0)

# constant-flow-rate driver: after each step add a uniform shift to u so <u> == CFR (exact, div-free).
cfr_view = None
if CFR > 0:
    cap = s.field_view("u")
    if isinstance(cap, np.ndarray):          # host backend -> NumPy view
        uv = cap
    else:                                    # device backend -> zero-copy CuPy
        import cupy as cp; uv = cp.from_dlpack(cap)
    g = (uv.shape[0] - NX) // 2
    cfr_inner = uv[g:g+NX, g:g+NY, g:g+NZ]   # live device view of inner u
    def apply_cfr():
        d = CFR - float(cfr_inner.mean())   # uniform shift == effective body-force impulse
        cfr_inner[...] += d
        return d
    apply_cfr()
    print(f"[cfr] constant flow rate: hold <u>={CFR}  (ghost g={g})", flush=True)

# ---- diagnostics + accumulation --------------------------------------------
def profiles():
    u = s.get_u(); v = s.get_v(); w = s.get_w()
    Uy = u.mean(axis=(0, 2))
    up = u - Uy[None, :, None]
    vc = 0.5*(v + np.roll(v, 1, axis=1)); vcy = vc.mean(axis=(0, 2)); vp = vc - vcy[None, :, None]
    wy = w.mean(axis=(0, 2)); wp = w - wy[None, :, None]
    Ruu = (up*up).mean(axis=(0, 2)); Rvv = (vp*vp).mean(axis=(0, 2))
    Rww = (wp*wp).mean(axis=(0, 2)); Ruv = (up*vp).mean(axis=(0, 2))
    return Uy, Ruu, Rvv, Rww, Ruv, float(u.mean())

acc = {k: np.zeros(NY) for k in ("U", "uu", "vv", "ww", "uv")}
nacc = 0
ts = []   # time series rows
t0 = time.time()
nan = False
STATEVERY = int(os.environ.get("STATEVERY", 25))   # accumulate a profile sample every N steps (past STATSTART)
dsum = 0.0; ndsum = 0                                # accumulate CFR shift -> momentum-balance u_tau
for it in range(1, NSTEPS + 1):
    s.step()
    if CFR > 0:
        dd = apply_cfr()
        if it >= STATSTART:
            dsum += dd; ndsum += 1
    do_diag = (it % DIAG == 0 or it == 1)
    do_stat = (it >= STATSTART and it % STATEVERY == 0)
    if do_diag or do_stat:
        Uy, Ruu, Rvv, Rww, Ruv, Ub = profiles()
        if not np.all(np.isfinite(Uy)):
            print(f"[!] NaN at step {it}", flush=True); nan = True; break
        if do_stat:
            acc["U"] += Uy; acc["uu"] += Ruu; acc["vv"] += Rvv
            acc["ww"] += Rww; acc["uv"] += Ruv; nacc += 1
        if do_diag:
            utau_b = np.sqrt(nu*Uy[0]/0.5); utau_t = np.sqrt(nu*Uy[-1]/0.5)
            urms_pk = np.sqrt(Ruu.max()); ruv_pk = (-Ruv).max()
            tke_pk = (0.5*(Ruu+Rvv+Rww)).max()
            tplus = it*DT/nu
            rate = it/(time.time()-t0)
            print(f"  it={it:5d} t+={tplus:7.1f} Ub+={Ub:5.2f} "
                  f"u_tau=({utau_b:.3f},{utau_t:.3f}) urms_pk={urms_pk:.2f} "
                  f"-uv_pk={ruv_pk:.3f} tke_pk={tke_pk:.2f} nacc={nacc}  [{rate:.1f} it/s]", flush=True)
            ts.append([it, tplus, Ub, utau_b, utau_t, urms_pk, ruv_pk, tke_pk])

# ---- save ------------------------------------------------------------------
yplus_full = yc/nu
out = dict(yc=yc, yplus=yplus_full, nu=nu, Dplus=Dplus, Re_tau=RE_TAU,
          NX=NX, NY=NY, NZ=NZ, DT=DT, ts=np.array(ts),
          Lxp=NX*Dplus, Lzp=NZ*Dplus, nan=nan)
if nacc > 0:
    for k in acc:
        out["prof_"+k] = acc[k]/nacc
    out["nacc"] = nacc
# momentum-balance friction velocity: u_tau^2 = H * <shift>/dt  (CFR); == 1 by construction for CPG
if CFR > 0 and ndsum > 0:
    utau2 = H * (dsum/ndsum) / DT
    out["utau_cfr"] = float(np.sqrt(max(utau2, 0.0)))
    out["CFR"] = CFR
    print(f"[utau] momentum-balance u_tau = {out['utau_cfr']:.4f}  "
          f"Re_tau = {out['utau_cfr']*H/nu:.1f}", flush=True)
np.savez(f"{OUT}_stats.npz", **out)
# restart field (post-run)
try:
    np.savez(f"{OUT}_restart.npz", u=s.get_u(), v=s.get_v(), w=s.get_w())
except Exception as e:
    print("restart save failed:", e, flush=True)
print(f"[done] {NSTEPS} steps, {NX*NY*NZ/1e6:.1f}M cells, "
      f"{(time.time()-t0)/NSTEPS*1e3:.0f} ms/step, nacc={nacc}. wrote {OUT}_stats.npz", flush=True)
