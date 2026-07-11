#!/usr/bin/env python3
"""One-on-one MFIX-Exa HCS gas-solid run: the benchmark's own drag law (BVK/"BVK2" = Beetstra-van
der Hoef-Kuipers 2007), exact system (L* = 256x256x8, N = 50000, phi ~ 0.05, e = 0.8, rho* = 1000,
Re_T0 = 20). Saves hcs_gas_bvk.npz with the T(t*) trace, clustering index and x-y snapshots.

Evidence chain this run completes: the MFIX-Exa Fig 34 RIGHT panel is their own gas-solid run at
t* = 1000; FLYH18 (arXiv:1809.04173) + Yin et al. (JFM 727 R2, 2013) establish that the interstitial
gas causes an EARLIER onset of the velocity-vortex and clustering instabilities than the dry granular
HCS; our published dry run therefore clusters later. This run adds the gas at the benchmark's drag
law so the t* = 1000 states can be compared one-on-one.

Non-dim: d_p = 1 (rp = 0.5), T0 = 1 -> t* = t. rho_g = 1, mu = rho_g*d_p*sqrt(T0)/Re_T0 = 0.05.
rho_p = 1000 -> m_p = rho_p*Vp.

    PECLET_LOCAL_BUILD=flow:dem:coupling builds  python make_hcs_gas_bvk.py [t_end=1500]
"""
import os, sys, time
import numpy as np

_local = os.environ.get("PECLET_LOCAL_BUILD")
if _local:
    for p in _local.split(os.pathsep):
        sys.path.insert(0, p)
import peclet.flow as flow
import peclet.dem as dem
from peclet.coupling import CfdDem

def _np(a):
    return a.get() if hasattr(a, "get") and type(a).__module__.startswith("cupy") else np.asarray(a)

T_END = float(sys.argv[1]) if len(sys.argv) > 1 else 1500.0
Lx = Ly = 256; Lz = 8; rp = 0.5; N = 50_000; e = 0.8; T0 = 1.0
rho_g, mu_g = 1.0, 0.05                      # Re_T0 = rho_g*d_p*sqrt(T0)/mu_g = 20
rho_p = 1000.0; Vp = (4/3)*np.pi*rp**3; m_p = rho_p*Vp
phi = N*Vp/(Lx*Ly*Lz); dt = 0.02; nsteps = int(round(T_END/dt))
print(f"BVK gas-solid HCS: phi={phi:.4f} N={N} e={e} Re_T0=20 rho*={rho_p:.0f} "
      f"-> t*={T_END:.0f} in {nsteps} steps", flush=True)

rng = np.random.default_rng(1)               # same seed/init as the dry + wen_yu runs
P = rng.uniform([0, 0, 0], [Lx, Ly, Lz], (N, 3)).astype(np.float32)
v = rng.normal(0, np.sqrt(T0), (N, 3)).astype(np.float32); v -= v.mean(0)
def gT(V): vp = V - V.mean(0); return float((vp*vp).sum(1).mean()/3.0)
nb = 64; pois = 1/np.sqrt(N/nb**2)
def cidx(Pp):
    H, _, _ = np.histogram2d(Pp[:, 0] % Lx, Pp[:, 1] % Ly, bins=nb, range=[[0, Lx], [0, Ly]])
    return float((H.std()/H.mean())/pois)

d = dem.Simulation(N+64); d.initialize(shape_type=1, radius=rp); d.set_sphere_shape(rp)
d.set_domain((0, 0, 0), (Lx, Ly, Lz)); d.enable_periodicity(True, True, True)
d.set_gravity(0, 0, 0); d.set_material_params(e, 0.0, 0.0); d.set_solver_iterations(6, 4); d.set_dt(dt)
d.set_positions(np.c_[P, np.full(N, 1.0/m_p, np.float32)]); d.set_velocities(v)
s = flow.Solver(Lx, Ly, Lz); s.set_rho(rho_g); s.set_mu(mu_g); s.set_dt(dt)
for f in range(6): s.set_domain_bc(f, 0)     # all periodic
s.set_pressure_pcg(True, 30, 1e-6)
cpl = CfdDem(s, d, fluid_dt=dt, mu=mu_g, rho=rho_g, radius=rp, drag="beetstra",
             dem_substeps=1, periodic=(True, True, True), move_particles=True, porous=False)

ts, Trat, ci = [0.0], [1.0], [cidx(P)]
snaps = {500: None, 1000: None, 1500: None, 2000: None, 3000: None, 4000: None}
t0 = time.time()
for i in range(nsteps):
    cpl.step(); tstar = (i+1)*dt
    if (i+1) % 50 == 0:
        V = _np(d.get_velocities())[:N]; Pp = _np(d.get_positions())[:N]
        ts.append(tstar); Trat.append(gT(V)/T0); ci.append(cidx(Pp))
    for tgt in list(snaps):
        if snaps[tgt] is None and tstar >= tgt - 1e-9:
            snaps[tgt] = _np(d.get_positions())[:N, :2].copy()
    if (i+1) % 10000 == 0:
        print(f"  t*={tstar:6.0f}  T/T0={Trat[-1]:.3e}  cidx={ci[-1]:.2f}  "
              f"({(time.time()-t0)/(i+1)*1e3:.1f} ms/step, {(time.time()-t0)/60:.0f} min)", flush=True)
        np.savez("hcs_gas_bvk.npz", ts=np.array(ts), Trat=np.array(Trat), cidx=np.array(ci),
                 T0=T0, e=e, phi=phi, N=N, Lx=Lx, Ly=Ly, Lz=Lz, ReT0=20.0, nsteps=i+1,
                 **{f"xy_{k}": (vv if vv is not None else np.zeros((0, 2))) for k, vv in snaps.items()})
print(f"DONE {nsteps} steps to t*={T_END:.0f} in {(time.time()-t0)/60:.1f} min "
      f"(final T/T0={Trat[-1]:.2e}, cidx={ci[-1]:.2f})", flush=True)
np.savez("hcs_gas_bvk.npz", ts=np.array(ts), Trat=np.array(Trat), cidx=np.array(ci),
         T0=T0, e=e, phi=phi, N=N, Lx=Lx, Ly=Ly, Lz=Lz, ReT0=20.0, nsteps=nsteps,
         **{f"xy_{k}": (vv if vv is not None else np.zeros((0, 2))) for k, vv in snaps.items()})
print("saved hcs_gas_bvk.npz", flush=True)
