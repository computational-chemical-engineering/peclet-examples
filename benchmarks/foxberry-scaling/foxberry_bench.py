#!/usr/bin/env python
"""FoxBerry comparison benchmark for the peclet `flow` solver (MPI, CPU or GPU).

Reproduces the two 3-D strong-scaling cases of FoxBerry/scaling/Scaling.cpp on a grid favorable
to peclet's geometric multigrid (400^3 = 64.0M cells instead of FoxBerry's 401^3 = 64.5M; same
dx = 1/400, so identical particle resolution D/dx = 22.1):

  CASE=single  Case 2 "Single-Phase 3D Flow": unit box, inlet u=1 (west), outlet (east), no-slip
               walls elsewhere, rho=1, mu=1, dt = 0.1*dx/u = 2.5e-4, 100 steps.
  CASE=packed  Case 3 "Packed-Bed IBM": same box/BCs, inlet u=0.001, dt = 0.1*dx/u = 0.25,
               5000 static spheres at solid holdup 0.45 (bed from make_bed.py, cut-cell IBM),
               100 steps.

Differences from FoxBerry, all deliberate (see README):
  - 400^3, not 401^3 (odd axes never coarsen in peclet's MG);
  - the bed is dem-grown at the same N/holdup/radius (FoxBerry's PRNG is not reproducible here);
  - the initial velocity is 0 (flow has no velocity setter; FoxBerry starts at u_inlet) -- for a
    per-step timing this is immaterial;
  - solver tolerances are peclet production settings (recorded in the JSON), not 1e-14.

Timing mirrors the FoxBerry graphs: "execution time per step" = wall time of NSTEPS steps after
WARMUP steps, divided by NSTEPS.  JSON schema follows tgv_bench.py / spheres_bench.py so the
plotting conventions port over.

Launch:
    PACK=results/packing_foxberry_n5000_phi0.45_s0.npz CASE=packed \
        mpirun -np 4 python foxberry_bench.py
    srun --mpi=pmix --gpus-per-task=1 python foxberry_bench.py

Env:
    CASE          single | packed (default packed)
    PACK          packing npz from make_bed.py (required for CASE=packed)
    GN            global grid per axis (default 400; the domain is the unit cube)
    UIN           inlet velocity (default: 1.0 single / 0.001 packed)
    CO            Courant number for dt = CO*dx/UIN (default 0.1); DT overrides dt directly
    NSTEPS WARMUP measured / warmup steps (default 100 / 2)
    MGLEVELS      pressure MG depth (default 5 = full depth of 400; clamped to achievable)
    DECOMP_LEVELS coarse-first decomposition request (default 5; 0 = aligned ORB)
    PRESSURE      pcg (default) | vcycle | fcg | cheby
    PMAXIT PRTOL  pressure iteration cap / rel. tolerance (default 200 / 1e-8)
    VSWEEPS VRTOL momentum RB-GS sweep cap / tolerance stop (default 200 / 1e-3)
    BOTTOM        auto (default) | smoother | agglomerated
    ADV           1 = explicit Koren TVD advection (default), 0 = off
    BCMODE        foxberry (default: inlet/outlet/4 walls) | periodic (ABLATION: fully periodic
                  box driven by a body force instead -- isolates the cut-cell/domain-BC
                  interaction from the bed itself; see README "Open issue")
    OUT LABEL     output JSON path / free-form label
"""
import json
import os
import socket
import time

import numpy as np
from mpi4py import MPI

world = MPI.COMM_WORLD
_local = world.Split_type(MPI.COMM_TYPE_SHARED)
if os.environ.get("PECLET_BIND_GPU", "0") == "1":
    _vis = os.environ.get("CUDA_VISIBLE_DEVICES")
    _devs = _vis.split(",") if _vis else None
    if _devs and len(_devs) > 1:
        os.environ["CUDA_VISIBLE_DEVICES"] = _devs[_local.rank % len(_devs)]
    elif not _devs:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(_local.rank)
RANK, NP = world.rank, world.size


def p0(*a):
    if RANK == 0:
        print(*a, flush=True)


CASE = os.environ.get("CASE", "packed")
if CASE not in ("single", "packed"):
    raise SystemExit(f"unknown CASE={CASE!r} (single|packed)")
GN = int(os.environ.get("GN", 400))
GNX = GNY = GNZ = GN                      # FoxBerry's box is the unit cube
H = 1.0 / GN                              # dx (= 1/400 at the reference resolution)
UIN = float(os.environ.get("UIN", 1.0 if CASE == "single" else 1e-3))
CO = float(os.environ.get("CO", 0.1))
DT = float(os.environ.get("DT", CO * H / UIN))
NSTEPS = int(os.environ.get("NSTEPS", 100))
WARMUP = int(os.environ.get("WARMUP", 2))
# 7 is the full depth of 384 (= 2^7*3); the solver clamps to what the grid and the per-rank block
# actually allow, so this is also correct on 400^3 (which stops at 5: 400->200->100->50->25).
MGLEVELS = int(os.environ.get("MGLEVELS", 7))
DECOMP_LEVELS = int(os.environ.get("DECOMP_LEVELS", 7))
PRESSURE = os.environ.get("PRESSURE", "pcg")
PMAXIT = int(os.environ.get("PMAXIT", 200))
PRTOL = float(os.environ.get("PRTOL", 1e-8))
VSWEEPS = int(os.environ.get("VSWEEPS", 200))
VRTOL = float(os.environ.get("VRTOL", 1e-3))
BOTTOM = os.environ.get("BOTTOM", "auto")
ADV = int(os.environ.get("ADV", 1))
BCMODE = os.environ.get("BCMODE", "foxberry")
if BCMODE not in ("foxberry", "periodic", "walls"):
    raise SystemExit(f"unknown BCMODE={BCMODE!r} (foxberry|periodic|walls)")
RHO, MU = 1.0, float(os.environ.get("MU", 1.0))
OUT = os.environ.get("OUT", f"fb_{CASE}_np{NP}.json")
LABEL = os.environ.get("LABEL", "")

pk = None
XPER = False
SHIFT_X = 0.0
if CASE == "packed":
    PACK = os.environ.get("PACK", "")
    if not PACK:
        raise SystemExit("PACK=<packing npz from make_bed.py> is required for CASE=packed")
    pk = np.load(PACK)
    BED = str(pk["bed"]) if "bed" in pk.files else (
        "periodic" if ("xperiodic" in pk.files and bool(pk["xperiodic"])) else "yz-periodic")
    XPER = BED == "periodic"
    # FoxBerry shifts the bed 4 cells (of ITS 400^3 grid) off the inlet -- a physical 0.01, kept
    # as such at any resolution. The triply-periodic bed fills the box and is not shifted.
    SHIFT_X = 0.0 if XPER else 4.0 / 400.0
    # "walls" is the faithful FoxBerry bed: grown against six planes on the region boundary, so
    # whole spheres sit inside [0.01, 0.99] x [0,1] x [0,1] and NO axis is periodic. Its SDF
    # therefore takes no images at all. (FoxBerry's own generator insets centers by
    # radius+clearance on every non-periodic axis -- verified in ObjectCoordinateGenerator.cpp --
    # so its bed is wall-confined in all three directions, not clipped and not y/z-periodic.)
    # A y/z-only bed under fully periodic BCs has a broken seam at x=0/1: a sphere clipped at one
    # face does not continue at the other, and the 4-cell margins become a clear slot spanning the
    # whole cross-section -- a short circuit for a body-force-driven flow. Refuse rather than
    # silently measure that.
    if BCMODE == "periodic" and BED != "periodic":
        raise SystemExit(
            f"BCMODE=periodic needs a TRIPLY-periodic bed, but {os.path.basename(PACK)} is "
            f"bed={BED}. Regenerate with BED=periodic make_bed.py.")
    if BCMODE in ("foxberry", "walls") and BED == "periodic":
        raise SystemExit(
            f"BCMODE={BCMODE} expects a wall-confined or FoxBerry-placed bed, but "
            f"{os.path.basename(PACK)} is triply periodic. Use the BED=walls bed.")

from peclet import flow  # noqa: E402

assert getattr(flow, "has_mpi", False), "flow was NOT built with PECLET_FLOW_MPI=ON"
if DECOMP_LEVELS:
    flow.set_decomposition_levels(DECOMP_LEVELS)
origin, size = flow.mpi_block(GNX, GNY, GNZ)
ox, oy, oz = origin
lnx, lny, lnz = size

p0(f"[cfg] case={CASE}  global {GNX}^3 = {GNX**3 / 1e6:.1f}M cells  ranks={NP}  "
   f"backend={flow.execution_space}  uin={UIN:g}  dt={DT:g}  mu={MU:g}  adv={ADV}  "
   f"levels={MGLEVELS} decomp={DECOMP_LEVELS}  pressure={PRESSURE}(maxit={PMAXIT},"
   f"rtol={PRTOL:g})  momentum(sweeps<={VSWEEPS},rtol={VRTOL:g})  bottom={BOTTOM}  "
   f"steps={WARMUP}+{NSTEPS}")

_bus = "-"
if flow.execution_space == "Cuda":
    try:
        import cupy as cp

        _bus = cp.cuda.runtime.deviceGetPCIBusId(cp.cuda.runtime.getDevice())
    except Exception as e:
        _bus = f"<unknown:{type(e).__name__}>"
_blocks = world.gather((RANK, socket.gethostname(), _bus, origin, size), root=0)
if RANK == 0:
    for rr, hh, bb, oo, ss in _blocks[: min(8, NP)]:
        print(f"  rank {rr}: block {ss[0]}x{ss[1]}x{ss[2]} at {oo}  {hh} {bb}", flush=True)
    if NP > 8:
        vols = [ss[0] * ss[1] * ss[2] for _, _, _, _, ss in _blocks]
        print(f"  ... {NP} blocks, imbalance max/min = {max(vols) / min(vols):.3f}", flush=True)

# ---- geometry ---------------------------------------------------------------------------------
phi_vox = 0.0
nsph = 0
if CASE == "packed":
    # Rank-local analytic SDF: union of spheres in cell units.  Periodic images are applied on
    # every axis the BED is periodic on -- y/z always (period 1 = the domain height/depth, so a
    # wall-crossing sphere is filled consistently from the other side), and x as well for the
    # triply-periodic bed. For the FoxBerry bed x is deliberately NOT wrapped: its spheres are
    # clipped at the inlet/outlet, which is what its placement rule produces.
    t0 = time.perf_counter()
    r_phys = float(pk["r_phys"])
    c_cells = (pk["centers"] * r_phys + np.array([SHIFT_X, 0.0, 0.0])) * GN
    r_cells = pk["scales"] * r_phys * GN
    BAND = 4.0
    sdf = np.full((lnx, lny, lnz), 1e30, order="F")
    xc = ox + np.arange(lnx) + 0.5
    yc = oy + np.arange(lny) + 0.5
    zc = oz + np.arange(lnz) + 0.5
    blk_lo = np.array([ox, oy, oz], np.float64)
    blk_hi = blk_lo + np.array([lnx, lny, lnz], np.float64)
    _im = {"periodic": ((-1, 0, 1), (-1, 0, 1), (-1, 0, 1)),   # triply periodic
           "yz-periodic": ((0,), (-1, 0, 1), (-1, 0, 1)),      # legacy: y/z images, x clipped
           "walls": ((0,), (0,), (0,))}[BED]                   # wall-confined: no images at all
    shifts = [np.array([sx, sy, sz], np.float64) * GN
              for sx in _im[0] for sy in _im[1] for sz in _im[2]]
    for sh in shifts:
        cs = c_cells + sh
        reach = r_cells + BAND
        m = np.all((cs + reach[:, None] > blk_lo) & (cs - reach[:, None] < blk_hi), axis=1)
        for cx, cy, cz, rr in zip(cs[m, 0], cs[m, 1], cs[m, 2], r_cells[m]):
            i0, i1 = np.searchsorted(xc, [cx - rr - BAND, cx + rr + BAND])
            j0, j1 = np.searchsorted(yc, [cy - rr - BAND, cy + rr + BAND])
            k0, k1 = np.searchsorted(zc, [cz - rr - BAND, cz + rr + BAND])
            if i0 >= i1 or j0 >= j1 or k0 >= k1:
                continue
            d = np.sqrt((xc[i0:i1, None, None] - cx) ** 2 + (yc[None, j0:j1, None] - cy) ** 2
                        + (zc[None, None, k0:k1] - cz) ** 2) - rr
            np.minimum(sdf[i0:i1, j0:j1, k0:k1], d, out=sdf[i0:i1, j0:j1, k0:k1])
    sdf = np.asfortranarray(np.clip(sdf, -1e3, 1e3))
    nsolid = world.allreduce(int((sdf < 0).sum()), op=MPI.SUM)
    phi_vox = nsolid / float(GN**3)
    nsph = int(pk["nspheres"])
    if BED == "periodic":
        # Triply periodic: the union fills the box, so the voxel fraction IS the holdup.
        phi_exp, lo, hi = float(pk["holdup"]), 0.01, 0.01
    elif BED == "walls":
        # Wall-confined: every sphere is whole and inside, so the domain fraction is exactly
        # holdup x region volume = 0.45 x 0.98, with no clipping loss.
        phi_exp, lo, hi = float(pk["holdup"]) * float(np.prod(pk["region"])), 0.01, 0.01
    else:
        # y/z-periodic: holdup over the 0.98-wide region, less the caps clipped at the x ends.
        phi_exp, lo, hi = float(pk["holdup"]) * 0.98, 0.03, 0.005
    p0(f"[sdf] built in {time.perf_counter() - t0:.1f}s  domain solid fraction={phi_vox:.4f} "
       f"(expected {phi_exp:.4f}, bed={BED})")
    if not (phi_exp - lo < phi_vox < phi_exp + hi):
        p0(f"FATAL: solid fraction {phi_vox:.4f} out of range -- bad bed/mapping. Refusing.")
        world.Barrier()
        raise SystemExit(1)

# ---- solver -----------------------------------------------------------------------------------
s = flow.Solver(lnx, lny, lnz)
s.init_mpi(GNX, GNY, GNZ)
s.set_rho(RHO)
s.set_mu(MU)
s.set_dt(DT)
s.set_advection(bool(ADV))
s.set_velocity_solver_params(VSWEEPS, VRTOL)
s.set_pressure_multigrid(True, MGLEVELS)
if PRESSURE == "pcg":
    s.set_pressure_pcg(True, PMAXIT, PRTOL)
elif PRESSURE == "fcg":
    s.set_pressure_fcg(True, PMAXIT, PRTOL)
elif PRESSURE == "cheby":
    s.set_pressure_chebyshev(True, PMAXIT, PRTOL)
elif PRESSURE != "vcycle":
    raise SystemExit(f"unknown PRESSURE={PRESSURE!r} (pcg|vcycle|fcg|cheby)")
s.set_pressure_bottom(BOTTOM)

# Domain BCs (before geometry): west inlet, east outlet, four no-slip walls -- FoxBerry's map.
if BCMODE == "foxberry":
    s.set_domain_bc(0, 2, UIN, 0.0, 0.0)   # -x inflow
    s.set_domain_bc(1, 3)                  # +x outflow
    for f in (2, 3, 4, 5):
        s.set_domain_bc(f, 1)              # y/z no-slip walls
elif BCMODE == "walls":
    # Ablation: six no-slip walls (Neumann pressure everywhere), body-force driven -- separates
    # the wall/Neumann half of the BC hierarchy from the inflow/outflow (Dirichlet) half.
    for f in range(6):
        s.set_domain_bc(f, 1)
    s.set_body_force(float(os.environ.get("F", 1e-3)), 0.0, 0.0)
else:
    # Ablation: fully periodic, body-force driven. Physics is NOT FoxBerry's -- this exists only
    # to separate the cut-cell operator from the domain-BC hierarchy in the investigation.
    s.set_body_force(float(os.environ.get("F", 1e-3)), 0.0, 0.0)

if CASE == "packed":
    s.set_solid(sdf, cutcell_pressure=True, pressure_coarse="rediscretized")
else:
    allfluid = np.full((lnx, lny, lnz), 1e3, order="F")
    s.set_pressure_geometry(allfluid)


def gmean_u():
    u = s.get_u()
    tot = world.allreduce(float(u.sum()), op=MPI.SUM)
    return tot / float(GN**3)


# ---- warmup (operator build, PCG bound estimation, flow start-up) -----------------------------
p0(f"[run] warmup {WARMUP} steps...")
for i in range(WARMUP):
    t0 = time.perf_counter()
    s.step()
    p0(f"[run] warmup {i + 1}/{WARMUP} done ({time.perf_counter() - t0:.1f}s, "
       f"{s.last_pressure_iterations()} pressure iters)")

# ---- measured steps ---------------------------------------------------------------------------
phases = ("step", "predictor", "momentum", "projection", "pressure_allreduce")
acc = {p: [] for p in phases}
acc["pressure_allreduce_count"] = []
iters = []
world.Barrier()
t0 = time.perf_counter()
_hb = max(1, NSTEPS // 10)
for istep in range(NSTEPS):
    s.step()
    if (istep + 1) % _hb == 0:
        p0(f"[run] step {istep + 1}/{NSTEPS}  ({s.last_pressure_iterations()} pressure iters)")
    t = s.last_step_timers()
    for p in phases:
        acc[p].append(t[p])
    acc["pressure_allreduce_count"].append(t["pressure_allreduce_count"])
    iters.append(s.last_pressure_iterations())
t1 = time.perf_counter()
wall = world.allreduce(t1 - t0, op=MPI.MAX)
stats = {}
for key, v in acc.items():
    m = float(np.mean(v))
    stats[key] = {"max": world.allreduce(m, op=MPI.MAX), "min": world.allreduce(m, op=MPI.MIN)}
it_mean = float(np.mean(iters))
# The MAX matters as much as the mean: a run where only SOME steps cap has a mean below PMAXIT
# and looks converged, while its step time is part convergence and part cap. Recorded so the
# plotter can reject it (measured 2026-09-01: np=1536 packed averaged 122 with steps at 200).
it_max = int(np.max(iters))
it_capped = int(np.sum(np.asarray(iters) >= PMAXIT))
cells = GN**3
ms_step = 1e3 * wall / NSTEPS
mcells = cells * NSTEPS / wall / 1e6
umean = gmean_u()
maxdiv = s.max_open_divergence()
p0(f"[perf] {ms_step:.1f} ms/step ({wall:.1f}s for {NSTEPS} steps)  {mcells:.1f} Mcell/s "
   f"({mcells / NP:.2f}/rank)  pressure iters/step {it_mean:.1f} (max {it_max}"
   + (f", {it_capped}/{NSTEPS} steps CAPPED -- INVALID)" if it_capped else ")"))
p0("[phases, rank-max ms/step] "
   + "  ".join(f"{p}={1e3 * stats[p]['max']:.1f}" for p in phases)
   + f"  allreduce_count={stats['pressure_allreduce_count']['max']:.0f}")
p0(f"[sanity] <u>={umean:.6e} (superficial; -> {UIN:g} at steady state)  "
   f"max|div(open*u)|={maxdiv:.3e}")

if RANK == 0:
    out = {
        "label": LABEL, "case": CASE, "np": NP, "backend": flow.execution_space,
        # Which module was imported -- the float vs -DPECLET_FLOW_MREAL_DOUBLE build is not
        # otherwise visible from Python, and it decides whether a high-contrast bed converges.
        "build": os.path.basename(os.path.dirname(os.path.dirname(
            os.path.dirname(flow.__file__)))) if hasattr(flow, "__file__") else "",
        "omp_threads": os.environ.get("OMP_NUM_THREADS", ""),
        "global": [GNX, GNY, GNZ], "cells": cells,
        "n_spheres": nsph, "phi_voxel": phi_vox,
        "pack": os.path.basename(os.environ.get("PACK", "")), "bed": BED,
        "uin": UIN, "mu": MU, "dt": DT, "adv": ADV, "bcmode": BCMODE,
        "pressure": PRESSURE, "pmaxit": PMAXIT, "prtol": PRTOL,
        "mglevels": MGLEVELS, "decomp_levels": DECOMP_LEVELS,
        "vsweeps": VSWEEPS, "vrtol": VRTOL, "bottom": BOTTOM,
        "nsteps": NSTEPS, "warmup": WARMUP,
        "ms_per_step": ms_step, "seconds_total": wall,
        "mcells_per_s": mcells, "mcells_per_s_per_rank": mcells / NP,
        "pressure_iters_per_step": it_mean, "pressure_iters_max": it_max,
        "pressure_steps_capped": it_capped, "phase_seconds_per_step": stats,
        "u_mean_final": umean, "max_div_final": maxdiv,
        "blocks": [{"rank": rr, "host": hh, "gpu": bb, "origin": list(oo), "size": list(ss)}
                   for rr, hh, bb, oo, ss in _blocks],
        "gpu_aware_env": os.environ.get("PECLET_CORE_GPU_AWARE_MPI", ""),
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"[out] {OUT}", flush=True)

world.Barrier()
MPI.Finalize()
os._exit(0)  # skip Kokkos-finalize teardown abort (known CUDA atexit issue)
