#!/usr/bin/env python
"""Distributed turbulent plane-channel DNS on the peclet `flow` solver (MPI, multi-GPU or multi-core).

Runs the same physics as channel_dns.py but decomposed across MPI ranks with the core ORB
BlockDecomposer (`flow.mpi_block`). Benchmarked against Moser-Kim-Mansour 1999 (Re_tau=180).

Launch (one rank per GPU):
    srun --mpi=pmix python channel_dns_mpi.py            # on Snellius (SLURM sets the allocation)
    mpirun -np 4 --map-by ppr:1:gpu python channel_dns_mpi.py
Or CPU (one rank per core-group):
    OMP_NUM_THREADS=8 mpirun -np 24 python channel_dns_mpi.py

Grid units dx=dy=dz=1 (isotropic). u_tau=1 by choice -> stats in wall units. CPG f=2/gny pins
u_tau=1 (momentum balance); CFR (hold bulk) reaches a stationary state faster and measures u_tau.

Env: GNX GNY GNZ NSTEPS DT DIAG STATSTART STATEVERY ADV CFR OUT RE_TAU SEED
"""
import os, sys, time
import numpy as np
from mpi4py import MPI

# ---- one GPU per node-local rank: set visibility BEFORE importing peclet -----------------------
# Kokkos::initialize() takes default device 0, so each rank must see exactly ONE distinct GPU.
# Pick the node-local-rank-th of whatever GPUs are visible (works whether SLURM exposed all 4 to
# every task, or none). Set PECLET_BIND_GPU=0 to disable (CPU runs, or if the launcher already binds).
world = MPI.COMM_WORLD
_local = world.Split_type(MPI.COMM_TYPE_SHARED)
if os.environ.get("PECLET_BIND_GPU", "1") == "1":
    _vis = os.environ.get("CUDA_VISIBLE_DEVICES")
    _devs = _vis.split(",") if _vis else None
    os.environ["CUDA_VISIBLE_DEVICES"] = (_devs[_local.rank % len(_devs)] if _devs
                                          else str(_local.rank))
RANK, NP = world.rank, world.size

def p0(*a):
    if RANK == 0: print(*a, flush=True)

GNX = int(os.environ.get("GNX", 384)); GNY = int(os.environ.get("GNY", 128)); GNZ = int(os.environ.get("GNZ", 128))
NSTEPS = int(os.environ.get("NSTEPS", 20000)); DT = float(os.environ.get("DT", 0.012))
DIAG = int(os.environ.get("DIAG", 500)); STATSTART = int(os.environ.get("STATSTART", 10**9))
STATEVERY = int(os.environ.get("STATEVERY", 25)); ADV = int(os.environ.get("ADV", 0))
CFR = float(os.environ.get("CFR", 0.0)); OUT = os.environ.get("OUT", "chan_mpi")
RE_TAU = float(os.environ.get("RE_TAU", 180.0)); SEED = int(os.environ.get("SEED", 1234))

nu = (GNY/2.0)/RE_TAU; H = GNY/2.0; fbody = 2.0/GNY; Dplus = 1.0/nu

from peclet import flow
assert getattr(flow, "has_mpi", False), "flow was NOT built with PECLET_FLOW_MPI=ON"
origin, size = flow.mpi_block(GNX, GNY, GNZ)          # this rank's ORB block
ox, oy, oz = origin; lnx, lny, lnz = size
# GUARD: the ORB must not split the wall-normal (y) direction. A no-slip domain wall + an internal
# y block-boundary decouples the two halves at the centreline (validated: periodic x/z splits are
# bit-exact, a y-split diverges). For the standard elongated channel grid ORB keeps y whole up to
# ~32 ranks; beyond that reduce ranks or lengthen the x/z box.
_ysplit = world.allreduce(1 if lny < GNY else 0, op=MPI.SUM)
if _ysplit:
    if RANK == 0:
        sys.stderr.write(f"FATAL: ORB split the wall-normal y on {_ysplit}/{NP} ranks (unsupported for "
                         f"domain-wall channel BCs). Use fewer ranks (<= ~32 for this grid) or a longer box.\n")
    sys.exit(1)
p0(f"[cfg] global {GNX}x{GNY}x{GNZ} = {GNX*GNY*GNZ/1e6:.1f}M cells  nu={nu:.4f} f={fbody:.5g} "
   f"Delta+={Dplus:.3f} Lx+={GNX*Dplus:.0f} Ly+={GNY*Dplus:.0f} Lz+={GNZ*Dplus:.0f}  "
   f"ranks={NP}  backend={flow.execution_space}  dt={DT} adv={'SOU' if ADV==0 else 'Koren'}")
for r in range(NP):
    if r == RANK: print(f"  rank {r}: block origin=({ox},{oy},{oz}) size=({lnx},{lny},{lnz})", flush=True)
    world.Barrier()

# ---- local initial condition: global Reichardt mean (global y) + per-rank low-pass noise --------
kap = 0.41
def reichardt(yp):
    return (1/kap)*np.log1p(kap*yp) + 7.8*(1 - np.exp(-yp/11) - (yp/11)*np.exp(-0.33*yp))
gy = (np.arange(oy, oy+lny) + 0.5)                    # global cell-center y of this block
dwall = np.minimum(gy, GNY - gy); yp = dwall/nu
rng = np.random.default_rng(SEED + 100*RANK)
def lp(shape, cutoff=0.06):
    g = rng.standard_normal(shape); G = np.fft.rfftn(g, axes=(0, 1, 2))
    kx = np.fft.fftfreq(shape[0])[:, None, None]; ky = np.fft.fftfreq(shape[1])[None, :, None]
    kz = np.fft.rfftfreq(shape[2])[None, None, :]
    G[np.sqrt(kx*kx+ky*ky+kz*kz) > cutoff] = 0.0
    o = np.fft.irfftn(G, s=shape, axes=(0, 1, 2)); return o/(o.std()+1e-12)
env = ((dwall/nu/15.0)*np.exp(1 - dwall/nu/15.0))[None, :, None]
A = float(os.environ.get("NOISE", 1.0))               # NOISE=0 -> deterministic Reichardt IC (validation)
u0 = np.asfortranarray(reichardt(yp)[None, :, None] + A*2.6*env*lp((lnx, lny, lnz)))
v0 = np.asfortranarray(A*1.1*env*lp((lnx, lny, lnz)))
w0 = np.asfortranarray(A*1.5*env*lp((lnx, lny, lnz)))

# ---- solver setup (same config on every rank; solver applies wall BCs only to boundary blocks) --
s = flow.Solver(lnx, lny, lnz)
s.init_mpi(GNX, GNY, GNZ)
s.set_rho(1.0); s.set_mu(nu); s.set_dt(DT)
s.set_advection(True); s.set_advection_scheme(ADV)
s.set_velocity_solver_params(20)
s.set_pressure_multigrid(True, 5); s.set_pressure_pcg(True, 80, 1e-4); s.set_pressure_warmstart(True)
s.set_domain_bc(2, 1); s.set_domain_bc(3, 1)          # no-slip walls on -y,+y ; x,z periodic
s.set_body_force(0.0 if CFR > 0 else fbody, 0.0, 0.0)
s.set_pressure_geometry(np.asfortranarray(np.full((lnx, lny, lnz), 1e30)))
s.set_state(u0, v0, w0)

# ---- constant-flow-rate forcing: global bulk via Allreduce, uniform shift on every rank ---------
apply_cfr = None; dsum = 0.0; ndsum = 0
if CFR > 0:
    cap = s.field_view("u")
    if isinstance(cap, np.ndarray):
        uview = cap
    else:
        import cupy as cp; uview = cp.from_dlpack(cap)
    g = (uview.shape[0] - lnx)//2
    inner = uview[g:g+lnx, g:g+lny, g:g+lnz]
    gcells = GNX*GNY*GNZ
    def apply_cfr():
        loc = np.array([float(inner.sum())], dtype=np.float64)
        tot = np.zeros(1, dtype=np.float64); world.Allreduce(loc, tot, op=MPI.SUM)
        d = CFR - tot[0]/gcells
        inner[...] += d
        return d
    apply_cfr()

# ---- distributed statistics: local (x,z) sums binned into global-y, Allreduced ------------------
gkeys = ("U", "uu", "vv", "ww", "uv")
gacc = {k: np.zeros(GNY) for k in gkeys}; gcnt = np.zeros(GNY); nacc = 0
def local_profiles():
    u = s.get_u(); v = s.get_v(); w = s.get_w()
    Uy = u.sum(axis=(0, 2)); N = u.shape[0]*u.shape[2]
    vc = v.copy(); vc[:, 1:, :] = 0.5*(v[:, 1:, :] + v[:, :-1, :])
    uu = (u*u).sum(axis=(0, 2)); vv = (vc*vc).sum(axis=(0, 2)); ww = (w*w).sum(axis=(0, 2))
    uv = (u*vc).sum(axis=(0, 2)); vs = vc.sum(axis=(0, 2)); ws = w.sum(axis=(0, 2))
    return u, Uy, uu, vv, ww, uv, vs, ws, N

def reduce_global(local_y, N):
    """place a length-lny local sum into global-y bins and Allreduce."""
    buf = np.zeros(GNY); buf[oy:oy+lny] = local_y
    out = np.zeros(GNY); world.Allreduce(buf, out, op=MPI.SUM); return out

def accumulate():
    global nacc
    u, Uy, uu, vv, ww, uv, vs, ws, N = local_profiles()
    cbuf = np.zeros(GNY); cbuf[oy:oy+lny] = N; gc = np.zeros(GNY); world.Allreduce(cbuf, gc, op=MPI.SUM)
    gU = reduce_global(Uy, N); gUU = reduce_global(uu, N); gVV = reduce_global(vv, N)
    gWW = reduce_global(ww, N); gUV = reduce_global(uv, N); gVS = reduce_global(vs, N); gWS = reduce_global(ws, N)
    with np.errstate(invalid="ignore", divide="ignore"):
        mU = gU/gc; mUU = gUU/gc; mVV = gVV/gc; mWW = gWW/gc; mUV = gUV/gc; mVS = gVS/gc; mWS = gWS/gc
    # central moments (Reynolds stresses)
    gacc["U"] += mU; gacc["uu"] += mUU - mU*mU; gacc["vv"] += mVV - mVS*mVS
    gacc["ww"] += mWW - mWS*mWS; gacc["uv"] += mUV - mU*mVS; gcnt[:] = gc
    nacc += 1
    return mU, mUU - mU*mU, mVV - mVS*mVS, mUV - mU*mVS

# ---- time loop --------------------------------------------------------------------------------
ts = []; t0 = time.time()
for it in range(1, NSTEPS+1):
    s.step()
    if CFR > 0:
        dd = apply_cfr()
        if it >= STATSTART: dsum += dd; ndsum += 1
    do_diag = (it % DIAG == 0 or it == 1); do_stat = (it >= STATSTART and it % STATEVERY == 0)
    if do_diag or do_stat:
        mU, Ruu, Rvv, Ruv = accumulate() if do_stat else (None,)*4
        if do_diag:
            # a light diagnostic that doesn't double-accumulate
            u = s.get_u(); Uy_l = u.sum(axis=(0,2)); N = u.shape[0]*u.shape[2]
            gU = reduce_global(Uy_l, N)
            cbuf = np.zeros(GNY); cbuf[oy:oy+lny] = N; gc = np.zeros(GNY); world.Allreduce(cbuf, gc, op=MPI.SUM)
            with np.errstate(invalid="ignore"): Uprof = gU/gc
            locsum = np.array([float(u.sum()), float(u.size)]); tot = np.zeros(2); world.Allreduce(locsum, tot, op=MPI.SUM)
            Ub = tot[0]/tot[1]
            utau = np.sqrt(nu*Uprof[0]/0.5)
            if RANK == 0:
                tp = it*DT/nu; rate = it/(time.time()-t0)
                print(f"  it={it:6d} t+={tp:7.1f} Ub+={Ub:5.2f} u_tau~{utau:.3f} nacc={nacc} [{rate:.1f} it/s]", flush=True)
                ts.append([it, tp, Ub, utau, nacc])

# ---- save (rank 0) ----------------------------------------------------------------------------
if RANK == 0:
    yc = np.arange(GNY) + 0.5
    out = dict(yc=yc, yplus=yc/nu, nu=nu, Dplus=Dplus, Re_tau=RE_TAU, NX=GNX, NY=GNY, NZ=GNZ,
               DT=DT, ts=np.array(ts), Lxp=GNX*Dplus, Lzp=GNZ*Dplus, ranks=NP)
    if nacc > 0:
        for k in gkeys: out["prof_"+k] = gacc[k]/nacc
        out["nacc"] = nacc
    if CFR > 0 and ndsum > 0:
        locd = np.array([dsum, ndsum]); totd = np.zeros(2)  # dsum is global already (same on all ranks)
        utau2 = H*(dsum/ndsum)/DT; out["utau_cfr"] = float(np.sqrt(max(utau2, 0.0))); out["CFR"] = CFR
        print(f"[utau] momentum-balance u_tau = {out['utau_cfr']:.4f}  Re_tau = {out['utau_cfr']*H/nu:.1f}", flush=True)
    np.savez(f"{OUT}_stats.npz", **out)
    print(f"[done] {NSTEPS} steps, {GNX*GNY*GNZ/1e6:.0f}M cells, {NP} ranks, "
          f"{(time.time()-t0)/NSTEPS*1e3:.0f} ms/step, nacc={nacc}. wrote {OUT}_stats.npz", flush=True)
world.Barrier()
