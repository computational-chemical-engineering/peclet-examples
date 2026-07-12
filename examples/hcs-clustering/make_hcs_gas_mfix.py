#!/usr/bin/env python3
"""One-for-one MFIX-Exa "Clustering in the HCS" benchmark run (gas-solid), cached for the gallery
page as hcs_gas_mfix.npz (a multi-hour GPU run, so it is not executed inline).

Settings pinned from the public MFIX-Exa input decks + source (see the page's callout):
  * exact system:  L* = 256 x 256 x 8 (particle diameters), N = 50 000, phi ~ 0.05, e = 0.8,
                   rho_p/rho_g = 1000, Re_T0 = 20, periodic, g = 0, to t* = 10 000 (t* = t sqrt(T0)/dp)
  * drag:          Tang et al. (2015) — the correlation MFIX-Exa's "BVK2" drag option executes
  * spheres:       smooth (mu = 0 in the MFIX decks; tangential force Coulomb-clamped to zero)
  * fluid:         volume-averaged incompressible gas (porous=True: d(eps)/dt + div(eps u) = 0;
                   MFIX-Exa advects the superficial velocity and projects div(eps u) = 0)
  * CFD grid:      Delta* = 2 particle diameters (their decks + grid heuristic), h = 2

Non-dim: d_p = 1 (rp = 0.5), T0 = 1 -> t* = t. rho_g = 1, mu = rho_g*d_p*sqrt(T0)/Re_T0 = 0.05.

    PECLET_LOCAL_BUILD=<flow>:<dem>:<coupling builds>  python make_hcs_gas_mfix.py [t_end=10000]
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

T_END = float(sys.argv[1]) if len(sys.argv) > 1 else 10000.0
Lx = Ly = 256; Lz = 8; rp = 0.5; N = 50_000; e = 0.8; T0 = 1.0
rho_g, mu_g = 1.0, 0.05                      # Re_T0 = rho_g*d_p*sqrt(T0)/mu_g = 20
rho_p = 1000.0; Vp = (4/3)*np.pi*rp**3; m_p = rho_p*Vp
phi = N*Vp/(Lx*Ly*Lz); dt = 0.02; nsteps = int(round(T_END/dt))
print(f"MFIX-Exa HCS one-for-one: phi={phi:.4f} N={N} e={e} Re_T0=20 rho*={rho_p:.0f} "
      f"Tang drag, volume-averaged gas, Delta*=2 -> t*={T_END:.0f} in {nsteps} steps", flush=True)

rng = np.random.default_rng(1)               # same seed/init as the dry run (hcs_mfix.npz)
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
s = flow.Solver(Lx//2, Ly//2, Lz//2); s.set_rho(rho_g); s.set_mu(mu_g); s.set_dt(dt)  # Delta* = 2
for f in range(6): s.set_domain_bc(f, 0)     # all periodic
s.set_pressure_pcg(True, 30, 1e-6)
cpl = CfdDem(s, d, fluid_dt=dt, mu=mu_g, rho=rho_g, radius=rp, drag="tang", h=2.0,
             dem_substeps=1, periodic=(True, True, True), move_particles=True, porous=True)
# Enforce div(eps u) = 0, dropping the d(eps)/dt RHS source — the SAME constraint MFIX-Exa runs
# (its include_depdt option is off by default, "under development"). With a trilinear deposit at
# Delta* = 2 the per-cell d(eps)/dt is atomically jagged and acts as a stochastic pressure forcing:
# with the term on, the measured particle T/T0 ROSE ~3x past the clustering plateau (no physical
# energy source exists) while the MFIX benchmark curve decays. (CfdDem enables porous continuity
# in its constructor, so set this AFTER building the coupler.)
s.set_porous_deps_dt(False)

ts, Trat, ci = [0.0], [1.0], [cidx(P)]
snaps = {1000: None, 2000: None, 3000: None, 5000: None, 10000: None}
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
        np.savez("hcs_gas_mfix.npz", ts=np.array(ts), Trat=np.array(Trat), cidx=np.array(ci),
                 T0=T0, e=e, phi=phi, N=N, Lx=Lx, Ly=Ly, Lz=Lz, ReT0=20.0, nsteps=i+1,
                 **{f"xy_{k}": (vv if vv is not None else np.zeros((0, 2))) for k, vv in snaps.items()})
print(f"DONE {nsteps} steps to t*={T_END:.0f} in {(time.time()-t0)/60:.1f} min "
      f"(final T/T0={Trat[-1]:.2e}, cidx={ci[-1]:.2f})", flush=True)
np.savez("hcs_gas_mfix.npz", ts=np.array(ts), Trat=np.array(Trat), cidx=np.array(ci),
         T0=T0, e=e, phi=phi, N=N, Lx=Lx, Ly=Ly, Lz=Lz, ReT0=20.0, nsteps=nsteps,
         **{f"xy_{k}": (vv if vv is not None else np.zeros((0, 2))) for k, vv in snaps.items()})
print("saved hcs_gas_mfix.npz", flush=True)
