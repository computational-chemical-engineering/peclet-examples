"""Canonical run: Verma et al. (2014, AIChE J 60:1632, doi 10.1002/aic.14393) X-ray bed,
glass case, AR = 1.0, U = 1.5 Umf — CFD-DEM reproduction with peclet.

Column D = 0.1 m (cut-cell cylinder), simulated height 0.36 m, uniform inflow (their porous
distributor), pressure outflow. Glass: dp = 1.0 mm, rho = 2526 kg/m3, e_n = 0.86 (their Table 6),
Umf = 0.68 m/s. Drag: Beetstra / van der Hoef (their ref 29). Grid h = D/32 = 3.125 mm = 3.1 dp.
N ~ 0.9 M grains -> static bed height ~0.10 m.

Post-processing mirrors the paper: bubbles = connected eps > 0.7 regions in horizontal planes,
equivalent diameter De = <sqrt(4A/pi)> (Eqs 1-2), rise velocity from the eps cross-correlation
between planes 10 mm apart (their Eq 7), porosity PDF with 0.04 bins.

Writes verma_bed.npz (plane series + diagnostics) + eps/particle snapshots for the movie.
Usage: python make_verma_bed.py <t_end_seconds> [outdir]
"""
import os, sys, time
for _p in os.environ.get("PECLET_LOCAL_BUILD", "").split(os.pathsep):
    if _p:
        sys.path.insert(0, _p)
import numpy as np
from peclet import flow, dem
from peclet.dem import build_wall_sdf
from peclet.coupling import CfdDem

t_end = float(sys.argv[1]) if len(sys.argv) > 1 else 7.0
outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))

# ---- the paper's system, in grid units (1 cell = h = D/32) ----
D_m, dp_m = 0.10, 1.0e-3
h_m = D_m / 32                                # 3.125 mm = 3.125 dp
rho_p, rho_g, mu_si = 2526.0, 1.2, 1.8e-5
Umf = 0.68
U_si = 1.5 * Umf
NX = NY = 34                                  # cylinder + one cell of wall padding each side
NZ = 116                                      # 0.3625 m ~ their 0.36 m simulated column
Rm, cxm = 16.0, 17.0                          # R = 0.05 m
dpc, rpc = dp_m / h_m, dp_m / h_m / 2         # grain: 0.32 cells
mu_c, g_c, U_c = mu_si / h_m**2, 9.81 / h_m, U_si / h_m
m_p = rho_p * (4 / 3) * np.pi * rpc**3
N = 965_000                                   # measured packing -> H0 = 0.10 m (AR = 1.0)
H_lid = 96.0                                  # grain lid (0.30 m); gas leaves above it
dt = 4.0e-4                                   # fluid step, s (20 DEM substeps of 20 us)
print(f"grid {NX}x{NY}x{NZ}, h = {h_m*1e3:.3f} mm = {h_m/dp_m:.2f} dp,  U = {U_si:.3f} m/s "
      f"= {U_c:.0f} cells/s,  N = {N:,}", flush=True)

# ---- gas: cut-cell cylinder, inflow floor at the superficial velocity, outflow roof ----
s = flow.Solver(NX, NY, NZ)
s.set_rho(rho_g); s.set_mu(mu_c); s.set_dt(dt)
s.set_domain_bc(4, 2, 0.0, 0.0, U_c)
s.set_domain_bc(5, 3)
for f in (0, 1, 2, 3):
    s.set_domain_bc(f, 1)
s.set_pressure_pcg(True, 50, 1e-6)
X, Y, _ = np.meshgrid(np.arange(NX) + .5, np.arange(NY) + .5, np.arange(NZ) + .5, indexing="ij")
s.set_solid(np.asfortranarray((Rm - np.hypot(X - cxm, Y - cxm)).astype(np.float64)).flatten(order="F"), True)

# ---- grains: pour a jittered lattice, settle to the packed bed ----
sp = 1.05 * dpc
nxy = int(2 * (Rm - 2 * rpc) / sp)
xs = cxm - (nxy / 2) * sp + (np.arange(nxy) + 0.5) * sp
pos, k = [], 0
while len(pos) < N:
    z = 2 * rpc + (k + 0.5) * sp
    for ix in range(nxy):
        for iy in range(nxy):
            if (xs[ix] - cxm) ** 2 + (xs[iy] - cxm) ** 2 < (Rm - 1.5 * rpc) ** 2:
                pos.append((xs[ix], xs[iy], z))
    k += 1
pos = np.array(pos[:N], np.float32)
pos[:, :2] += np.random.default_rng(7).uniform(-0.01, 0.01, (N, 2)).astype(np.float32)

d = dem.Simulation(int(1.15 * N) + 256)
d.initialize(shape_type=1, radius=rpc)
d.set_domain((0, 0, 0), (NX, NY, NZ)); d.enable_periodicity(False, False, False)
d.set_gravity(0, 0, -g_c)
d.set_material_params(0.86, 0.0, 0.1)         # e_n = 0.86 (their Table 6); glass-glass friction 0.1
d.set_dt(dt / 20)
def wall(p):
    return np.minimum.reduce([Rm - np.hypot(p[:, 0] - cxm, p[:, 1] - cxm), p[:, 2], H_lid - p[:, 2]])
build_wall_sdf(wall, ((0, 0, 0), (NX, NY, NZ)), resolution=160).add_to(d, restitution=0.86, friction=0.1)
d.set_positions(np.c_[pos, np.full(N, 1.0 / m_p, np.float32)])
d.set_velocities(np.zeros((N, 3), np.float32))
d.set_solver_iterations(120, 4)

t0 = time.time()
nset = 12000                                  # 0.24 s of pure DEM settling (pour falls ~0.1 m)
for _ in range(nset):
    d.step(dt / 20)
pz = d.get_positions()[:N, 2]
H0 = float(np.percentile(pz, 98)) * h_m
print(f"settled in {time.time()-t0:.0f}s: H0 = {H0*100:.1f} cm (target 10, AR = 1.0)", flush=True)

# ---- couple: Beetstra drag (their van der Hoef/Beetstra choice), porous gas, implicit drag ----
cpl = CfdDem(s, d, fluid_dt=dt, mu=mu_c, rho=rho_g, radius=rpc, drag="beetstra",
             dem_substeps=20, smooth_width=1.0, periodic=(False, False, False),
             move_particles=True, implicit_drag=True, porous=True)

# ---- measurement planes (paper: 5 and 10 cm + partners 10 mm above for the CCF) ----
zplanes_m = [0.05, 0.06, 0.10, 0.11]          # 10-mm pairs at both heights (their sims: 10 mm)
kz = [int(round(z / h_m)) for z in zplanes_m]
xi, yi = np.meshgrid(np.arange(NX) + .5, np.arange(NY) + .5, indexing="ij")
inmask = (np.hypot(xi - cxm, yi - cxm) < Rm - 0.5)
sample_every = 5                              # 2 ms frames (their images: 1 ms)
movie_every = int(round(0.010 / dt))          # 10 ms movie frames

nsteps = int(round(t_end / dt))
planes = np.zeros((nsteps // sample_every + 1, len(kz), NX, NY), np.float32)
dPs, tops, nsamp = [], [], 0
os.makedirs(os.path.join(outdir, "verma_frames"), exist_ok=True)
xp = cpl.xp
t0 = time.time()
for i in range(nsteps):
    cpl.step()
    if i % sample_every == 0:  # host copies only on sampling steps (they dominate otherwise)
        ep = cpl.last_eps
        ep = ep.get() if hasattr(ep, "get") else np.asarray(ep)
        gwidth = (ep.shape[0] - NX) // 2
        for j, kzz in enumerate(kz):
            planes[nsamp, j] = ep[gwidth:gwidth + NX, gwidth:gwidth + NY, gwidth + kzz]
        nsamp += 1
        p = s.get_p()
        p = p.get() if hasattr(p, "get") else np.asarray(p)
        dPs.append(float(np.nanmean(p[:, :, 1][inmask]) - np.nanmean(p[:, :, -2][inmask])) * h_m**2)
        pz = d.get_positions()[:N, 2]
        tops.append(float(np.percentile(pz, 98)) * h_m)
    if i % movie_every == 0:
        np.savez_compressed(os.path.join(outdir, "verma_frames", f"f{i//movie_every:05d}.npz"),
                            eps=ep[gwidth:gwidth + NX, gwidth:gwidth + NY, gwidth:gwidth + NZ].astype(np.float16))
    if i % 250 == 0:
        v = d.get_velocities()[:N]
        print(f"step {i}/{nsteps} t={i*dt:.2f}s ({time.time()-t0:.0f}s) |v|max={np.abs(v).max():.1f} "
              f"dP={dPs[-1]:.0f} top={tops[-1]*100:.1f}cm", flush=True)

np.savez_compressed(os.path.join(outdir, "verma_bed.npz"),
                    planes=planes[:nsamp], kz=np.array(kz), zplanes=np.array(zplanes_m),
                    dPs=np.array(dPs), tops=np.array(tops), dt=dt, sample_every=sample_every,
                    diag_every=sample_every,
                    h_m=h_m, N=N, U_si=U_si, Umf=Umf, H0=H0, inmask=inmask,
                    W_over_A=N * (rho_p * np.pi / 6 * dp_m**3) * 9.81 / (np.pi * 0.05**2))
print(f"done: {nsteps} steps in {(time.time()-t0)/3600:.1f} h -> verma_bed.npz", flush=True)
