#!/usr/bin/env python
"""Stokes permeability scaling benchmark for the peclet `flow` solver (MPI, GPU or CPU): creeping
flow through a DEM-grown random sphere packing, cut-cell or ghost-cell IBM.

Geometry comes from a `pack_bed.py` npz (sphere centers + scales, R = 1): every rank samples the
analytic union-of-spheres SDF over ITS OWN block (periodic images included), so the SDF is never
gathered and one packing serves any resolution -- the refine ladder resamples the same physical
bed, the upscale ladder gets a per-rung packing.

Two phases, one JSON:
  A perf    warmup + NSTEPS fixed steps: ms/step, per-phase breakdown, pressure iters/step,
            allreduce time/count (same fields as tgv_bench.py -> plots port over).
  B physics march to steady state (|d<u>|/<u> < MARCH_TOL, capped): permeability k/R^2,
            steps-to-steady, total pressure iterations.

Launch (one rank per GPU):
    PACK=packing.npz mpirun -np 4 python spheres_bench.py
    srun --mpi=pmix --gpus-per-task=1 --gpu-bind=per_task:1 python spheres_bench.py

Env:
    PACK          packing npz from pack_bed.py (required)
    GNX GNY GNZ   global grid (default: the packing's recorded rung grid)
    IBM           cutcell (default) | ghost
    GRID          staggered (default, flow.Solver) | collocated (flow.SolverColocated)
    FACEINTERP    collocated cut-cell treatment: 0 = plain (default), 9 = aperture + gpCenterGrad
                  (mode 9); ignored on the staggered grid, must be 0 with IBM=ghost
    GPORDER       ghost closure order "matrix,rhs" (default 2,2; 1,2 = the mixed/deferred mode)
    PUNDER        incremental-pressure under-relaxation omega_p (default 1.0 = off)
    BOTTOM        auto (default) | smoother | agglomerated  (pressure coarse-level solve)
    NSTEPS WARMUP phase-A measured / warmup steps (default 25 / 5)
    MARCH_TOL     phase-B relative steady tolerance on <u> (default 1e-5; 0 = skip phase B)
    MARCH_MAX     phase-B step cap (default 400)
    CHECK_EVERY   phase-B convergence check interval (default 5)
    MGLEVELS      pressure MG depth (default 7; solver clamps to the achievable depth)
    PRESSURE      pcg (default) | vcycle   (ghost runs its own MG-BiCGStab driver either way)
    PMAXIT PRTOL  pressure iterations cap / tolerance (default 300 / 1e-8)
    VSWEEPS       momentum RB-GS sweep cap (default 80 -- Stokes: diffusion dominates)
    WARMSTART     1 = seed each solve from previous phi (default 0: measured DIVERGENT on the steady Stokes march -- 192^3 bed blew up by step 400; opt-in for unsteady runs only)
    MU F DT       viscosity / body force / time step (default 0.1 / 1e-3 / 60 -- regression values)
    TRACE         1 = log <u>, max|u|,|v|,|w|, max|div| (the solve's TRUE residual) and pressure
                  iterations every march step (default 0)
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


PACK = os.environ.get("PACK", "")
if not PACK:
    raise SystemExit("PACK=<packing.npz from pack_bed.py> is required")
pk = np.load(PACK)
centers, scales, box = pk["centers"], pk["scales"], pk["box"]
GNX = int(os.environ.get("GNX", pk["gnx"]))
GNY = int(os.environ.get("GNY", pk["gny"]))
GNZ = int(os.environ.get("GNZ", pk["gnz"]))
IBM = os.environ.get("IBM", "cutcell")
GRID = os.environ.get("GRID", "staggered")       # staggered (flow.Solver) | collocated
FACEINTERP = int(os.environ.get("FACEINTERP", 0))  # collocated cut-cell treatment (0 | 9 | ...)
BOTTOM = os.environ.get("BOTTOM", "auto")
NSTEPS = int(os.environ.get("NSTEPS", 25))
WARMUP = int(os.environ.get("WARMUP", 5))
MARCH_TOL = float(os.environ.get("MARCH_TOL", 1e-5))
MARCH_MAX = int(os.environ.get("MARCH_MAX", 400))
CHECK_EVERY = int(os.environ.get("CHECK_EVERY", 5))
MGLEVELS = int(os.environ.get("MGLEVELS", 7))
PRESSURE = os.environ.get("PRESSURE", "pcg")
PMAXIT = int(os.environ.get("PMAXIT", 300))
PRTOL = float(os.environ.get("PRTOL", 1e-8))
VSWEEPS = int(os.environ.get("VSWEEPS", 80))
WARMSTART = int(os.environ.get("WARMSTART", 0))
MU = float(os.environ.get("MU", 0.1))
F = float(os.environ.get("F", 1e-3))
DT = float(os.environ.get("DT", 60.0))
PUNDER = float(os.environ.get("PUNDER", 1.0))  # incremental-pressure under-relaxation omega_p
GPORDER = os.environ.get("GPORDER", "2,2")  # ghost closure order "matrix,rhs" (IBM=ghost only)
TRACE = int(os.environ.get("TRACE", 0))   # 1 = per-march-step <u>/max|u| log (divergence forensics)
OUT = os.environ.get("OUT", f"spheres_bench_np{NP}.json")
LABEL = os.environ.get("LABEL", "")

# cells per sphere radius: the grid must sample the packing's box isotropically
cpr = np.array([GNX, GNY, GNZ]) / box
if not np.allclose(cpr, cpr[0], rtol=1e-9):
    raise SystemExit(f"grid {GNX}x{GNY}x{GNZ} is not isotropic over box {box}: {cpr}")
RCELLS = float(cpr[0])

from peclet import flow  # noqa: E402

assert getattr(flow, "has_mpi", False), "flow was NOT built with PECLET_FLOW_MPI=ON"
origin, size = flow.mpi_block(GNX, GNY, GNZ)
ox, oy, oz = origin
lnx, lny, lnz = size

p0(f"[cfg] global {GNX}x{GNY}x{GNZ} = {GNX * GNY * GNZ / 1e6:.1f}M cells  ranks={NP}  "
   f"backend={flow.execution_space}  grid={GRID}  IBM={IBM}  face_interp={FACEINTERP}  "
   f"bottom={BOTTOM}  spheres={len(centers)} "
   f"R={RCELLS:.1f} cells  phi={float(pk['phi']):.4f}  levels={MGLEVELS}  "
   f"pressure={PRESSURE}(maxit={PMAXIT},rtol={PRTOL:g},warmstart={WARMSTART})  "
   f"steps={WARMUP}+{NSTEPS} then march(tol={MARCH_TOL:g},max={MARCH_MAX})")

_bus = "-"
if flow.execution_space == "Cuda":
    try:
        import cupy as cp

        _bus = cp.cuda.runtime.deviceGetPCIBusId(cp.cuda.runtime.getDevice())
    except Exception as e:
        _bus = f"<unknown:{type(e).__name__}>"
_blocks = world.gather((RANK, socket.gethostname(), _bus, origin, size), root=0)
if RANK == 0:
    seen = {}
    for rr, hh, bb, oo, ss in _blocks:
        print(f"  rank {rr}: block {ss[0]}x{ss[1]}x{ss[2]} at {oo}  {hh} {bb}", flush=True)
        seen.setdefault((hh, bb), []).append(rr)
    dups = {kk: v for kk, v in seen.items() if len(v) > 1 and flow.execution_space == "Cuda"}
    if dups:
        print(f"  WARNING: GPUs shared by >1 rank (oversubscription): {dups}", flush=True)

# ---- rank-local analytic SDF: union of spheres, periodic images, cell units -------------------
t_sdf0 = time.perf_counter()
G = np.array([GNX, GNY, GNZ], np.float64)
c_cells = centers * RCELLS          # sphere centers in cell units, in [0, G)
r_cells = scales * RCELLS           # per-sphere radius in cells
BAND = 4.0                          # SDF accuracy band beyond the surface, in cells
sdf = np.full((lnx, lny, lnz), 1e30, order="F")
xc = ox + np.arange(lnx) + 0.5
yc = oy + np.arange(lny) + 0.5
zc = oz + np.arange(lnz) + 0.5
blk_lo = np.array([ox, oy, oz], np.float64)
blk_hi = blk_lo + np.array([lnx, lny, lnz], np.float64)
shifts = [np.array(s, np.float64) * G
          for s in np.stack(np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1],
                                        indexing="ij"), -1).reshape(-1, 3)]
ns_local = 0
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
        ns_local += 1
sdf = np.asfortranarray(np.clip(sdf, -1e3, 1e3))
nsolid = world.allreduce(int((sdf < 0).sum()), op=MPI.SUM)
phi_vox = nsolid / float(GNX * GNY * GNZ)
p0(f"[sdf] built in {time.perf_counter() - t_sdf0:.1f}s  voxel solid fraction={phi_vox:.4f} "
   f"(packing {float(pk['phi']):.4f})")
# Independent gate on the ARTIFACT, not the packer's self-report: an unresolved packing (overlapping
# spheres) has union volume < N*V_sphere, so the sampled fraction falls below the analytic phi.
# Seen in the wild (Snellius 2026-08-14, 2 of 6 rungs): dem's contact pipeline silently no-opped,
# get_max_overlap() reported ~0 past pack_bed's gate, phi_voxel came out 0.40 -> k was 4.2x off.
if abs(phi_vox - float(pk["phi"])) > 0.02:
    p0(f"FATAL: voxel solid fraction {phi_vox:.4f} vs packing phi {float(pk['phi']):.4f} -- "
       f"the bed in {PACK} is not a converged packing (overlapping spheres?). Refusing to run.")
    world.Barrier()
    raise SystemExit(1)

# ---- solver ------------------------------------------------------------------------------------
if GRID == "collocated":
    s = flow.SolverColocated(lnx, lny, lnz)
elif GRID == "staggered":
    s = flow.Solver(lnx, lny, lnz)
else:
    raise SystemExit(f"unknown GRID={GRID!r} (staggered|collocated)")
s.init_mpi(GNX, GNY, GNZ)
s.set_rho(1.0)
s.set_mu(MU)
s.set_dt(DT)
s.set_body_force(F, 0.0, 0.0)
s.set_advection(False)  # creeping Stokes
s.set_velocity_solver_params(VSWEEPS)
s.set_pressure_multigrid(True, MGLEVELS)
if PRESSURE == "pcg":
    s.set_pressure_pcg(True, PMAXIT, PRTOL)
elif PRESSURE != "vcycle":
    raise SystemExit(f"unknown PRESSURE={PRESSURE!r} (pcg|vcycle)")
if WARMSTART:
    s.set_pressure_warmstart(True)
s.set_pressure_bottom(BOTTOM)
if GRID == "collocated" and FACEINTERP:
    s.set_face_interp(FACEINTERP)   # before set_ghost_projection: ghost demands mode 0
if PUNDER != 1.0:
    s.set_pressure_underrelax(PUNDER)
if IBM == "ghost":
    _mo, _ro = (int(v) for v in GPORDER.split(","))
    # before set_solid; MG hierarchy = binary-openness surrogate
    s.set_ghost_projection(True, _mo, _ro)
elif IBM != "cutcell":
    raise SystemExit(f"unknown IBM={IBM!r} (cutcell|ghost)")
s.set_solid(sdf, cutcell_pressure=True, pressure_coarse="rediscretized")


def gmean_u():
    u = s.get_u()
    tot = world.allreduce(float(u.sum()), op=MPI.SUM)
    return tot / float(GNX * GNY * GNZ)


def trace_u():
    """(mean u, max|u|, max|v|, max|w|) -- per-step divergence monitor (TRACE=1 only)."""
    u, v, w = s.get_u(), s.get_v(), s.get_w()
    tot = world.allreduce(float(u.sum()), op=MPI.SUM)
    mx = [world.allreduce(float(np.abs(a).max()), op=MPI.MAX) for a in (u, v, w)]
    return (tot / float(GNX * GNY * GNZ), *mx)


# ---- phase A: performance ---------------------------------------------------------------------
p0(f"[run] warmup {WARMUP} steps...")
for i in range(WARMUP):
    s.step()
    p0(f"[run] warmup {i + 1}/{WARMUP} done")
phases = ("step", "predictor", "momentum", "projection", "pressure_allreduce")
acc = {p: [] for p in phases}
acc["pressure_allreduce_count"] = []
iters = []
world.Barrier()
t0 = time.perf_counter()
_hb = max(1, NSTEPS // 5)
for istep in range(NSTEPS):
    s.step()
    if (istep + 1) % _hb == 0:
        p0(f"[run] step {istep + 1}/{NSTEPS}")
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
cells = GNX * GNY * GNZ
ms_step = 1e3 * wall / NSTEPS
mcells = cells * NSTEPS / wall / 1e6
p0(f"[perf] {ms_step:.1f} ms/step  {mcells:.1f} Mcell/s ({mcells / NP:.1f}/rank)  "
   f"pressure iters/step {it_mean:.1f}")
p0("[phases, rank-max ms/step] "
   + "  ".join(f"{p}={1e3 * stats[p]['max']:.1f}" for p in phases)
   + f"  allreduce_count={stats['pressure_allreduce_count']['max']:.0f}")

# ---- phase B: march to steady state, permeability ----------------------------------------------
march = None
if MARCH_TOL > 0:
    t0 = time.perf_counter()
    prev, msteps, mit = 0.0, 0, 0
    for it in range(MARCH_MAX):
        s.step()
        msteps += 1
        mit += s.last_pressure_iterations()
        if TRACE:
            um, ux, vx, wx = trace_u()
            p0(f"[trace] step {msteps:4d}  <u>={um:.6e}  max|u|={ux:.6e}  max|v|={vx:.6e}  "
               f"max|w|={wx:.6e}  maxdiv={s.max_open_divergence():.4e}  "
               f"iters={s.last_pressure_iterations()}")
        if it % CHECK_EVERY == CHECK_EVERY - 1:
            m = gmean_u()
            if it >= 3 * CHECK_EVERY and abs(m - prev) < MARCH_TOL * (abs(m) + 1e-300):
                break
            prev = m
    twall = world.allreduce(time.perf_counter() - t0, op=MPI.MAX)
    umean = gmean_u()
    k_cells = MU * umean / F               # superficial Darcy permeability, cell^2
    k_R2 = k_cells / (RCELLS * RCELLS)     # in units of the sphere radius squared
    march = {"steps": msteps, "pressure_iters": mit, "seconds": twall,
             "converged": msteps < MARCH_MAX, "u_mean": umean,
             "k_cells2": k_cells, "k_over_R2": k_R2}
    p0(f"[march] {msteps} steps ({'converged' if march['converged'] else 'CAP'}) "
       f"{mit} pressure iters in {twall:.1f}s   k/R^2 = {k_R2:.6g}")

if RANK == 0:
    out = {
        "label": LABEL, "np": NP, "backend": flow.execution_space,
        "omp_threads": os.environ.get("OMP_NUM_THREADS", ""),
        "global": [GNX, GNY, GNZ], "cells": cells,
        "pack": os.path.basename(PACK), "n_spheres": int(len(centers)),
        "phi_pack": float(pk["phi"]), "phi_voxel": phi_vox, "seed": int(pk["seed"]),
        "rcells": RCELLS, "ibm": IBM, "grid": GRID, "face_interp": FACEINTERP, "bottom": BOTTOM, "gporder": GPORDER, "punder": PUNDER,
        "mu": MU, "f": F, "dt": DT, "pressure": PRESSURE, "pmaxit": PMAXIT, "prtol": PRTOL,
        "mglevels": MGLEVELS, "vsweeps": VSWEEPS, "warmstart": WARMSTART,
        "nsteps": NSTEPS, "warmup": WARMUP,
        "ms_per_step": ms_step, "mcells_per_s": mcells, "mcells_per_s_per_rank": mcells / NP,
        "pressure_iters_per_step": it_mean, "phase_seconds_per_step": stats,
        "march": march,
        "blocks": [{"rank": rr, "host": hh, "gpu": bb, "origin": list(oo), "size": list(ss)}
                   for rr, hh, bb, oo, ss in _blocks],
        "gpu_aware_env": os.environ.get("PECLET_CORE_GPU_AWARE_MPI", ""),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[out] {OUT}", flush=True)

world.Barrier()
MPI.Finalize()
os._exit(0)  # skip Kokkos-finalize teardown abort (known CUDA atexit issue)
