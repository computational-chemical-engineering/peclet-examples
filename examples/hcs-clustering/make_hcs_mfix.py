#!/usr/bin/env python3
"""Run the MFIX-Exa Clustering-in-the-HCS benchmark at its exact system size and save hcs_mfix.npz
for the gallery page to load (a long GPU run, so it is cached rather than executed inline).

MFIX-Exa case: periodic box L* = 256 x 256 x 8 (particle diameters), N = 50 000 grains, solids
fraction phi ~ 0.05, restitution e = 0.8, cooled to the benchmark's non-dimensional time t* = 10000
(t* = t*sqrt(T0)/d_p). The clustering instability is COLLISIONAL (the Goldhirsch–Zanetti mechanism);
for the benchmark's density ratio rho_p/rho_g = 1000 the gas drag is a minor energy sink, so we carry
the collisional system to the full t* range where the instability develops into filaments. The
companion `hcs_gas_1000.npz` records the *gas-coupled* run (Re_T0 = 20) to t* = 1000 to show the gas
lowers the granular temperature only modestly and leaves the clustering picture unchanged.

Non-dim: d_p = 1 (rp = 0.5), T0 = 1 so sqrt(T0) = 1 and t* = t.

    PECLET_LOCAL_BUILD=.../flow/build:.../dem/build:.../coupling/build python make_hcs_mfix.py
"""
import os, sys, time
import numpy as np

_local = os.environ.get("PECLET_LOCAL_BUILD")
if _local:
    for p in _local.split(os.pathsep):
        sys.path.insert(0, p)
import peclet.dem as dem

def _np(a):
    return a.get() if hasattr(a, "get") and type(a).__module__.startswith("cupy") else np.asarray(a)

Lx = Ly = 256; Lz = 8; rp = 0.5; N = 50_000; e = 0.8; T0 = 1.0
Vp = (4/3)*np.pi*rp**3; phi = N*Vp/(Lx*Ly*Lz)
dt = 0.02; T_STAR_END = 10000.0; nsteps = int(round(T_STAR_END/dt))
n_den = N/(Lx*Ly*Lz); g0 = (1-phi/2)/(1-phi)**3
enskog_slope = (1-e**2)/3 * 2*np.sqrt(np.pi) * n_den * (2*rp)**2 * g0 * np.sqrt(T0)
print(f"phi={phi:.4f} N={N} e={e} g0={g0:.3f} enskog_slope={enskog_slope:.4f} "
      f"-> collisional (dry) HCS to t*={T_STAR_END:.0f} in {nsteps} steps", flush=True)

rng = np.random.default_rng(1)
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
d.set_positions(np.c_[P, np.ones(N, np.float32)]); d.set_velocities(v)

ts, Trat, ci = [0.0], [1.0], [cidx(P)]
snap_targets = {1000: None, 2000: None, 5000: None, 10000: None}
t0 = time.time()
for i in range(nsteps):
    d.step(dt); tstar = (i+1)*dt
    if (i+1) % 50 == 0:                          # sample the trajectory every t* = 1
        V = _np(d.get_velocities())[:N]; Pp = _np(d.get_positions())[:N]
        ts.append(tstar); Trat.append(gT(V)/T0); ci.append(cidx(Pp))
    for tgt in list(snap_targets):
        if snap_targets[tgt] is None and tstar >= tgt - 1e-9:
            snap_targets[tgt] = _np(d.get_positions())[:N, :2].copy()
    if (i+1) % 50000 == 0:
        print(f"  t*={tstar:6.0f}  T/T0={Trat[-1]:.3e}  cidx={ci[-1]:.2f}  "
              f"({(time.time()-t0)/(i+1)*1e3:.1f} ms/step, {(time.time()-t0)/60:.0f} min)", flush=True)
        np.savez("hcs_mfix.npz", ts=np.array(ts), Trat=np.array(Trat), cidx=np.array(ci),
                 enskog_slope=enskog_slope, T0=T0, e=e, phi=phi, N=N, Lx=Lx, Ly=Ly, Lz=Lz, nsteps=i+1,
                 **{f"xy_{k}": (v if v is not None else np.zeros((0, 2))) for k, v in snap_targets.items()})
print(f"DONE {nsteps} steps to t*={T_STAR_END:.0f} in {(time.time()-t0)/60:.1f} min  "
      f"(final T/T0={Trat[-1]:.2e}, cidx={ci[-1]:.2f})", flush=True)
np.savez("hcs_mfix.npz", ts=np.array(ts), Trat=np.array(Trat), cidx=np.array(ci),
         enskog_slope=enskog_slope, T0=T0, e=e, phi=phi, N=N, Lx=Lx, Ly=Ly, Lz=Lz, nsteps=nsteps,
         **{f"xy_{k}": (v if v is not None else np.zeros((0, 2))) for k, v in snap_targets.items()})
print("saved hcs_mfix.npz", flush=True)
