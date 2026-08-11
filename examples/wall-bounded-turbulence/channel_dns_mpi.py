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

Doubles as the *scaling instrument* for the channel-scaling benchmark: every run reports
warmup-excluded steady timing with the solver's per-phase breakdown (predictor / momentum /
projection), the pressure-solver iteration count and its global-reduction (MPI_Allreduce) time and
count, plus the CFR forcing's own all-reduce, and writes it all as JSON (BENCH_OUT). The physics
settings are unchanged; only the measurement is added.

Env: GNX GNY GNZ NSTEPS DT DIAG STATSTART STATEVERY ADV CFR OUT RE_TAU SEED NOISE WARMUP CKPT
Solver knobs (defaults = the production DNS configuration):
    VSWEEPS VTOL     momentum RB-GS sweep cap / tolerance stop (VTOL=0 -> legacy fixed count)
    PRESSURE         pcg (default) | cheb | vcycle
    PMAXIT PRTOL     pressure driver iteration cap / tolerance (80 / 1e-4)
    MGLEVELS         pressure multigrid depth (5)
    MEANSCOPE        pressure mean-removal scope: fine (default) | all
Instrument:
    BENCH_OUT        JSON path for the timing record (default "<OUT>_bench.json")
    LABEL            free-form label copied into the JSON (e.g. "snellius-h100")
    HB               heartbeat: print progress every HB steps (0 = off, DIAG already prints)
"""
import json, os, socket, sys, time
import numpy as np
from mpi4py import MPI

# ---- one GPU per rank -------------------------------------------------------------------------
# PREFERRED: let SLURM bind one GPU per task (srun --gpus-per-task=1 --gpu-bind=per_task:1). Then
# each task is cgroup-isolated to its own GPU (which it sees as device 0) and we must NOT touch
# CUDA_VISIBLE_DEVICES -- Kokkos::initialize() picks device 0 = the right GPU. This is the robust path.
# LEGACY: PECLET_BIND_GPU=1 hand-picks the node-local-rank-th visible GPU (only for launchers that
# expose ALL GPUs to every task and do NOT cgroup-isolate). Default is now 0 (trust SLURM).
world = MPI.COMM_WORLD
_local = world.Split_type(MPI.COMM_TYPE_SHARED)
if os.environ.get("PECLET_BIND_GPU", "0") == "1":
    _vis = os.environ.get("CUDA_VISIBLE_DEVICES")
    _devs = _vis.split(",") if _vis else None
    # only remap when MORE than one GPU is visible to this task; a single visible GPU is already isolated
    if _devs and len(_devs) > 1:
        os.environ["CUDA_VISIBLE_DEVICES"] = _devs[_local.rank % len(_devs)]
    elif not _devs:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(_local.rank)
RANK, NP = world.rank, world.size

def p0(*a):
    if RANK == 0: print(*a, flush=True)

GNX = int(os.environ.get("GNX", 384)); GNY = int(os.environ.get("GNY", 128)); GNZ = int(os.environ.get("GNZ", 128))
NSTEPS = int(os.environ.get("NSTEPS", 20000)); DT = float(os.environ.get("DT", 0.012))
DIAG = int(os.environ.get("DIAG", 500)); STATSTART = int(os.environ.get("STATSTART", 10**9))
STATEVERY = int(os.environ.get("STATEVERY", 25)); ADV = int(os.environ.get("ADV", 0))
CFR = float(os.environ.get("CFR", 0.0)); OUT = os.environ.get("OUT", "chan_mpi")
RE_TAU = float(os.environ.get("RE_TAU", 180.0)); SEED = int(os.environ.get("SEED", 1234))
CKPT = int(os.environ.get("CKPT", 0))   # checkpoint every N steps -> restart-on-resubmit (0 = off)
# ---- solver knobs (defaults = the production DNS configuration) + instrument -------------------
VSWEEPS = int(os.environ.get("VSWEEPS", 20)); VTOL = float(os.environ.get("VTOL", 1e-2))
PRESSURE = os.environ.get("PRESSURE", "pcg")
PMAXIT = int(os.environ.get("PMAXIT", 80)); PRTOL = float(os.environ.get("PRTOL", 1e-4))
MGLEVELS = int(os.environ.get("MGLEVELS", 5)); MEANSCOPE = os.environ.get("MEANSCOPE", "fine")
GRAPHAMG = int(os.environ.get("GRAPHAMG", 0))   # force the agglomerated bottom solve
BOTTOM = os.environ.get("BOTTOM", "auto")      # coarse-solve policy: auto | smoother | agglomerated
BENCH_OUT = os.environ.get("BENCH_OUT", f"{OUT}_bench.json"); LABEL = os.environ.get("LABEL", "")
HB = int(os.environ.get("HB", 0))
_ckpt_field = f"{OUT}_ckpt_r{RANK}.npz"  # this rank's local (u,v,w) block
_ckpt_meta = f"{OUT}_ckpt_meta.npz"      # rank-0 step counter + accumulators (the restart "commit")

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
   f"ranks={NP}  backend={flow.execution_space}  dt={DT} adv={'SOU' if ADV==0 else 'Koren'}  "
   f"forcing={'CFR ' + repr(CFR) if CFR > 0 else 'CPG'}  "
   f"pressure={PRESSURE}(maxit={PMAXIT},rtol={PRTOL:g},levels={MGLEVELS},mean={MEANSCOPE})  "
   f"momentum={VSWEEPS} sweeps(rtol={VTOL:g})")
# Report the TRUE physical GPU per rank (host + PCI bus id) -- CUDA_VISIBLE_DEVICES is ambiguous under
# cgroup isolation (every isolated task shows "0"). Two ranks on the same host+bus = oversubscription.
# Gathered with the ORB block so the JSON carries the full decomposition record.
_host = socket.gethostname()
_bus = "?"
if flow.execution_space == "Cuda":
    try:
        import cupy as cp
        _bus = cp.cuda.runtime.deviceGetPCIBusId(cp.cuda.runtime.getDevice())
    except Exception as e:
        _bus = f"<unknown:{type(e).__name__}>"
_gpumap = world.gather((RANK, _host, _bus, origin, size), root=0)
if RANK == 0:
    print(f"  [gpu-bind] rank -> (block, host, GPU PCI bus):", flush=True)
    seen = {}
    for rr, hh, bb, oo, ss in _gpumap:
        print(f"    rank {rr}: block {ss[0]}x{ss[1]}x{ss[2]} at {oo}  {hh}  {bb}", flush=True)
        seen.setdefault((hh, bb), []).append(rr)
    dups = {k: v for k, v in seen.items() if len(v) > 1 and flow.execution_space == "Cuda"}
    if dups:
        print(f"  [gpu-bind] WARNING: GPUs shared by >1 rank (oversubscription -> bad scaling): {dups}", flush=True)
    else:
        print(f"  [gpu-bind] OK: every rank on a distinct physical GPU", flush=True)

# ---- initial condition designed to TRIGGER + SUSTAIN transition at low Re_tau ------------------
# Reichardt mean + streamwise ROLLS (x-invariant vortices) that lift up STREAKS via the
# self-sustaining cycle, + broadband noise. All perturbation scales are set in WALL UNITS
# (resolution-independent), so refining the grid does not shrink the seeded structures into the
# viscous range (the old cell-scale noise decayed at fine dx -> relaminarization). Streaks are
# seeded at spanwise wavelength LAMZ+ ~ 110 (the observed streak spacing); a strong amplitude and
# a constant-pressure-gradient (CPG) drive make transition robust — see the run scripts.
kap = 0.41
def reichardt(yp):
    return (1/kap)*np.log1p(kap*yp) + 7.8*(1 - np.exp(-yp/11) - (yp/11)*np.exp(-0.33*yp))
gy = (np.arange(oy, oy+lny) + 0.5)                    # global cell-center y of this block
dwall = np.minimum(gy, GNY - gy); yp = dwall/nu
rng = np.random.default_rng(SEED + 100*RANK)
def lp(shape, lmin_plus=40.0):
    # keep only wavelengths > lmin_plus WALL UNITS (cutoff in cycles/cell = Dplus/lmin_plus).
    cut = min(Dplus/lmin_plus, 0.45)
    g = rng.standard_normal(shape); G = np.fft.rfftn(g, axes=(0, 1, 2))
    kx = np.fft.fftfreq(shape[0])[:, None, None]; ky = np.fft.fftfreq(shape[1])[None, :, None]
    kz = np.fft.rfftfreq(shape[2])[None, None, :]
    G[np.sqrt(kx*kx+ky*ky+kz*kz) > cut] = 0.0
    o = np.fft.irfftn(G, s=shape, axes=(0, 1, 2)); return o/(o.std()+1e-12)
# near-wall envelope peaking at y+~20 (where streaks/rolls live), zero at wall + centre
fy = ((dwall/nu/20.0)*np.exp(1 - dwall/nu/20.0))[None, :, None]
# streamwise rolls: x-invariant, spanwise-periodic. u-streak ~ cos(kz z), roll v ~ sin(kz z).
zc = (np.arange(oz, oz + lnz) + 0.5)[None, None, :]
phase = 2*np.pi*zc / max(110.0/Dplus, 4.0)            # spanwise wavelength ~110 wall units
streak = np.cos(phase); roll = np.sin(phase)
A = float(os.environ.get("NOISE", 1.0))               # 0 -> mean only (validation); scales the perturbation
u0 = np.asfortranarray(reichardt(yp)[None, :, None] + A*(4.0*fy*streak + 2.0*fy*lp((lnx, lny, lnz))))
v0 = np.asfortranarray(A*(1.5*fy*roll + 1.0*fy*lp((lnx, lny, lnz))))
w0 = np.asfortranarray(A*(1.5*fy*lp((lnx, lny, lnz))))

# ---- solver setup (same config on every rank; solver applies wall BCs only to boundary blocks) --
s = flow.Solver(lnx, lny, lnz)
s.init_mpi(GNX, GNY, GNZ)
s.set_rho(1.0); s.set_mu(nu); s.set_dt(DT)
s.set_advection(True); s.set_advection_scheme(ADV)
# Momentum: tolerance stop (end the sweep loop once the max increment has contracted to VTOL of the
# first sweep's; VSWEEPS is the cap). The channel's diffusion number nu*dt ~ 0.013 is easy, so this
# exits in a few sweeps instead of always running the cap. VTOL=0 restores the legacy fixed count.
s.set_velocity_solver_params(VSWEEPS, VTOL)
s.set_pressure_multigrid(True, MGLEVELS)
if PRESSURE == "pcg":
    s.set_pressure_pcg(True, PMAXIT, PRTOL)
elif PRESSURE == "cheb":
    s.set_pressure_chebyshev(True, PMAXIT, PRTOL)
elif PRESSURE != "vcycle":
    raise SystemExit(f"unknown PRESSURE={PRESSURE!r} (pcg|cheb|vcycle)")
s.set_pressure_warmstart(True)
s.set_pressure_mean_removal(MEANSCOPE)
s.set_pressure_bottom(BOTTOM)
if GRAPHAMG:
    # The geometric hierarchy is block-local: an axis stops coarsening once a rank's block turns
    # odd, so at high rank counts the coarsest GLOBAL grid is far from coarse. This replaces that
    # bottom with an agglomerated algebraic solve. Applied at the set_pressure_geometry call below.
    s.set_pressure_graph_amg(True)
s.set_domain_bc(2, 1); s.set_domain_bc(3, 1)          # no-slip walls on -y,+y ; x,z periodic
s.set_body_force(0.0 if CFR > 0 else fbody, 0.0, 0.0)
s.set_pressure_geometry(np.asfortranarray(np.full((lnx, lny, lnz), 1e30)))

# ---- restart (resume fields) or fresh IC --------------------------------------------------------
# On resubmit, pick up this rank's checkpointed block instead of the Reichardt IC. The accumulators
# and step counter are restored below (after they are defined). Requires the SAME grid + rank count.
it0 = 0
_restarting = CKPT > 0 and os.path.exists(_ckpt_meta) and os.path.exists(_ckpt_field)
if _restarting:
    ck = np.load(_ckpt_field)
    s.set_state(np.asfortranarray(ck["u"]), np.asfortranarray(ck["v"]), np.asfortranarray(ck["w"]))
    p0(f"[restart] resumed fields from {OUT}_ckpt_r*.npz")
else:
    s.set_state(u0, v0, w0)

# ---- constant-flow-rate forcing: global bulk via Allreduce, uniform shift on every rank ---------
apply_cfr = None; dsum = 0.0; ndsum = 0
if CFR > 0:
    cap = s.field_view("u")
    if isinstance(cap, np.ndarray):
        uview = cap
    else:
        try:
            import cupy as cp; uview = cp.from_dlpack(cap)
        except Exception as e:
            if RANK == 0:
                sys.stderr.write(f"\nCFR-ERROR: constant-flow-rate needs CuPy for the on-device shift, "
                                 f"but it is unavailable: {type(e).__name__}: {e}\n"
                                 f"  fix:  pip install cupy-cuda12x   (into {sys.prefix})\n\n")
            world.Barrier(); sys.exit(2)
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

# ---- restore accumulators on restart, and define the checkpoint writer -------------------------
ts = []
if _restarting:
    meta = np.load(_ckpt_meta, allow_pickle=True)
    it0 = int(meta["it"]); nacc = int(meta["nacc"]); dsum = float(meta["dsum"]); ndsum = int(meta["ndsum"])
    for k in gkeys:
        gacc[k] = meta["gacc_" + k].copy()
    ts = [list(r) for r in meta["ts"]] if meta["ts"].size else []
    p0(f"[restart] resumed at step {it0}, nacc={nacc}, ndsum={ndsum}")

def checkpoint(it):
    # Each rank writes its local block; rank 0 then writes the meta (the commit). Atomic replace so a
    # kill mid-write can't corrupt a checkpoint. Restart replays from the last committed meta.
    # NB: tmp names end in .npz because np.savez appends .npz to a name that lacks it.
    tmp = _ckpt_field[:-4] + ".tmp.npz"
    np.savez(tmp, u=s.get_u(), v=s.get_v(), w=s.get_w()); os.replace(tmp, _ckpt_field)
    world.Barrier()
    if RANK == 0:
        mtmp = _ckpt_meta[:-4] + ".tmp.npz"
        np.savez(mtmp, it=it, nacc=nacc, dsum=dsum, ndsum=ndsum, ts=np.array(ts, dtype=object),
                 **{f"gacc_{k}": gacc[k] for k in gkeys})
        os.replace(mtmp, _ckpt_meta)
    world.Barrier()

# ---- time loop --------------------------------------------------------------------------------
WARMUP = int(os.environ.get("WARMUP", 50))   # steps to exclude from the steady-state timing
t0 = time.time(); t_warm = None; it_warm = 0
if _restarting:
    t_warm = t0; it_warm = it0   # timing is meaningless across a restart; anchor it here
# Per-phase instrument (steady window only): device-fenced solver phases + the pressure solve's
# global-reduction time/count, plus the CFR forcing's own Allreduce, which lives OUTSIDE the solver.
PHASES = ("step", "predictor", "momentum", "projection", "pressure_allreduce")
acc = {p: [] for p in PHASES}; acc["pressure_allreduce_count"] = []; acc["momentum_sweeps"] = []
acc["cfr"] = []; p_iters = []
for it in range(it0 + 1, NSTEPS+1):
    if it == WARMUP + 1:
        world.Barrier(); t_warm = time.time(); it_warm = it - 1   # start steady clock after warmup
    s.step()
    t_cfr = 0.0
    if CFR > 0:
        _tc = time.perf_counter(); dd = apply_cfr(); t_cfr = time.perf_counter() - _tc
        if it >= STATSTART: dsum += dd; ndsum += 1
    if it > WARMUP:
        tm = s.last_step_timers()
        for p in PHASES: acc[p].append(tm[p])
        acc["pressure_allreduce_count"].append(tm["pressure_allreduce_count"])
        acc["momentum_sweeps"].append(tm["momentum_sweeps"])
        acc["cfr"].append(t_cfr); p_iters.append(s.last_pressure_iterations())
    if HB > 0 and it % HB == 0:
        p0(f"  [hb] it={it}/{NSTEPS}  {(time.time()-t0)/(it-it0)*1e3:.0f} ms/step avg")
    do_diag = (DIAG > 0 and (it % DIAG == 0 or it == 1)); do_stat = (it >= STATSTART and it % STATEVERY == 0)
    if do_diag or do_stat:
        mU, Ruu, Rvv, Ruv = accumulate() if do_stat else (None,)*4
        if do_diag:
            # light live diagnostic (doesn't double-accumulate). Includes a peak -<u'v'>+ so you can
            # SEE turbulence sustaining vs relaminarizing in real time: turbulent ~0.5-0.7, laminar ~0.
            u = s.get_u(); v = s.get_v()
            Uy_l = u.sum(axis=(0,2)); N = u.shape[0]*u.shape[2]
            gU = reduce_global(Uy_l, N)
            cbuf = np.zeros(GNY); cbuf[oy:oy+lny] = N; gc = np.zeros(GNY); world.Allreduce(cbuf, gc, op=MPI.SUM)
            with np.errstate(invalid="ignore"): Uprof = gU/gc
            vc = v.copy(); vc[:, 1:, :] = 0.5*(v[:, 1:, :] + v[:, :-1, :])
            gUV = reduce_global((u*vc).sum(axis=(0,2)), N); gVS = reduce_global(vc.sum(axis=(0,2)), N)
            with np.errstate(invalid="ignore"):
                uvprof = gUV/gc - (gU/gc)*(gVS/gc)   # -<u'v'> in the lower half is positive
            locsum = np.array([float(u.sum()), float(u.size)]); tot = np.zeros(2); world.Allreduce(locsum, tot, op=MPI.SUM)
            Ub = tot[0]/tot[1]
            utau = np.sqrt(nu*Uprof[0]/0.5)
            uvpk = float(np.nanmax(np.abs(uvprof)))/max(utau, 1e-9)**2
            if RANK == 0:
                tp = it*DT/nu; rate = it/(time.time()-t0)
                print(f"  it={it:6d} t+={tp:7.1f} Ub+={Ub:5.2f} u_tau~{utau:.3f} -uv+pk={uvpk:.3f} "
                      f"nacc={nacc} [{rate:.1f} it/s]", flush=True)
                ts.append([it, tp, Ub, utau, nacc])
    if CKPT > 0 and it % CKPT == 0:
        checkpoint(it)   # survive the SLURM walltime limit -> resubmit resumes from here

# ---- steady-state timing (exclude warmup) -----------------------------------------------------
world.Barrier(); t_end = time.time()
nmeas = NSTEPS - it_warm
steady_ms = (t_end - t_warm)/nmeas*1e3 if (t_warm and nmeas > 0) else float('nan')
mcells = GNX*GNY*GNZ/1e6
if RANK == 0:
    print(f"[timing] steady {steady_ms:.1f} ms/step over {nmeas} steps (warmup {WARMUP} excluded) | "
          f"{mcells:.0f}M cells, {NP} GPU(s) = {mcells/NP:.1f}M/GPU | "
          f"{mcells*1e6/(steady_ms*1e-3)/1e6:.0f} Mcell-updates/s", flush=True)

# Per-phase: mean over the measured steps on this rank, then max/min over ranks. The spread is the
# load-imbalance indicator; the rank-max is what the (barrier-synchronised) step actually costs.
stats = {}
for key, v in acc.items():
    m = float(np.mean(v)) if v else float("nan")
    stats[key] = {"max": world.allreduce(m, op=MPI.MAX), "min": world.allreduce(m, op=MPI.MIN)}
it_mean = world.allreduce(float(np.mean(p_iters)) if p_iters else float("nan"), op=MPI.MAX)
if RANK == 0 and p_iters:
    print("[phases, rank-max ms/step] "
          + "  ".join(f"{p}={1e3*stats[p]['max']:.1f}" for p in PHASES)
          + f"  cfr_allreduce={1e3*stats['cfr']['max']:.1f}"
          + f"  | pressure iters/step {it_mean:.1f}"
          + f"  allreduces/step {stats['pressure_allreduce_count']['max']:.0f}"
          + f"  momentum sweeps/step {stats['momentum_sweeps']['max']:.1f}", flush=True)
    rec = {
        "label": LABEL, "np": NP, "backend": flow.execution_space,
        "omp_threads": os.environ.get("OMP_NUM_THREADS", ""),
        "global": [GNX, GNY, GNZ], "cells": GNX*GNY*GNZ, "cells_per_rank": GNX*GNY*GNZ/NP,
        "re_tau": RE_TAU, "nu": nu, "dt": DT, "adv": ADV, "forcing": "CFR" if CFR > 0 else "CPG",
        "cfr": CFR, "pressure": PRESSURE, "pmaxit": PMAXIT, "prtol": PRTOL, "mglevels": MGLEVELS,
        "meanscope": MEANSCOPE, "graphamg": GRAPHAMG, "bottom": BOTTOM, "vsweeps": VSWEEPS, "vtol": VTOL,
        "nsteps": NSTEPS, "warmup": WARMUP, "measured_steps": nmeas,
        "ms_per_step": steady_ms, "mcells_per_s": mcells*1e3/steady_ms,
        "pressure_iters_per_step": it_mean,
        "momentum_sweeps_per_step": stats["momentum_sweeps"]["max"],
        "phase_seconds_per_step": stats,
        "blocks": [{"rank": rr, "host": hh, "gpu": bb, "origin": list(oo), "size": list(ss)}
                   for rr, hh, bb, oo, ss in _gpumap],
        "gpu_aware_env": os.environ.get("PECLET_CORE_GPU_AWARE_MPI", ""),
    }
    with open(BENCH_OUT, "w") as f:
        json.dump(rec, f, indent=1)
    print(f"[bench] wrote {BENCH_OUT}", flush=True)

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
    # Completion sentinel: we only reach here if the full loop ran to NSTEPS (a SLURM walltime kill
    # terminates the process mid-loop, before this). An auto-resubmit chain checks this to stop.
    with open(f"{OUT}.done", "w") as f:
        f.write(f"NSTEPS={NSTEPS} nacc={nacc}\n")
    print(f"[done] {NSTEPS} steps, {GNX*GNY*GNZ/1e6:.0f}M cells, {NP} ranks, "
          f"{(time.time()-t0)/NSTEPS*1e3:.0f} ms/step, nacc={nacc}. wrote {OUT}_stats.npz + {OUT}.done", flush=True)
world.Barrier()
# Exit hard AFTER outputs are written: skips Python/Kokkos finalize, which otherwise aborts with
# "Kokkos allocation deallocated after Kokkos::finalize" (poisons the exit code even on success).
# Finalize MPI first so the launcher sees an orderly shutdown instead of "exited improperly".
sys.stdout.flush(); sys.stderr.flush()
MPI.Finalize()
os._exit(0)
