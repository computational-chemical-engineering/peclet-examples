#!/usr/bin/env python
"""Taylor-Green vortex scaling benchmark for the peclet `flow` solver (MPI, GPU or CPU).

The measurement instrument of the parallel-scaling study: a triply periodic box (no walls, no IBM
solids) tiled with Taylor-Green vortices, so the domain can grow in any direction without boundary
complications and every cell does identical work. Reports warmup-excluded per-step wall times with
the solver's per-phase breakdown (predictor / momentum / projection), the pressure-solver iteration
count, and the pressure solve's global-reduction (MPI_Allreduce) time -- the latency-bound term of
distributed scaling -- as JSON.

Launch (one rank per GPU, or per core-group on CPU):
    mpirun -np 4 python tgv_bench.py
    OMP_NUM_THREADS=8 mpirun -np 6 python tgv_bench.py
    srun --gpus-per-task=1 --gpu-bind=per_task:1 python tgv_bench.py     # Snellius

Env (all optional):
    GNX GNY GNZ   global grid (default 256^3)
    TILE          TGV vortex tile size in cells (default GNY; one full vortex per tile)
    NSTEPS WARMUP measured / warmup steps (default 50 / 10)
    RE            tile Reynolds number U0*TILE/nu (default 100)
    CFL           dt = CFL * dx / U0 (default 0.2)
    ADV           advection scheme 0=SOU 1=Koren (default 0, matching the channel-DNS study)
    PRESSURE      pcg | cheb | vcycle  (default pcg)
    GRAPHAMG      1 = agglomerated GraphAMG bottom solve on the MG's coarsest level (default 0)
    MEANSCOPE     pressure mean-removal scope: fine (default; ~3x fewer allreduces/iter) | all
    VSWEEPS       momentum RB-GS sweep cap per component (default 20)
    VTOL          momentum tolerance stop: end the sweep loop once the max increment has
                  contracted to VTOL of the first sweep's (default 1e-2; 0 = fixed VSWEEPS
                  count). The TGV diffusion number ~0.13 exits after ~3-5 sweeps.
    PMAXIT PRTOL  pressure driver iterations cap / tolerance (default 200 / 1e-5)
    MGLEVELS      pressure MG depth (default 5)
    WARMSTART     1 = seed each solve from previous phi (default 1)
    CHECK         1 = Stokes-regime analytic check: overrides U0=0.01, nu=0.5 (advection
                  negligible, diffusion number nu*dt=0.1 well inside the smoother's range) and
                  compares KE decay against the exact backward-Euler factor (1+3 nu k^2 dt)^-2
                  per step (TGV is a Stokes eigenfunction). Use a small TILE (e.g. 32) so the
                  decay is measurable over a short run.
    OUT           output JSON path (default tgv_bench_np<NP>.json)
    LABEL         free-form label copied into the JSON (e.g. "snellius-h100")
"""
import json
import os
import socket
import time

import numpy as np
from mpi4py import MPI

# One GPU per rank: trust SLURM cgroup isolation (PECLET_BIND_GPU=0 default); legacy manual remap
# only for launchers that expose all GPUs to every task. Must happen BEFORE importing flow.
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


GNX = int(os.environ.get("GNX", 256))
GNY = int(os.environ.get("GNY", 256))
GNZ = int(os.environ.get("GNZ", 256))
TILE = int(os.environ.get("TILE", GNY))
NSTEPS = int(os.environ.get("NSTEPS", 50))
WARMUP = int(os.environ.get("WARMUP", 10))
RE = float(os.environ.get("RE", 100.0))
CFL = float(os.environ.get("CFL", 0.2))
ADV = int(os.environ.get("ADV", 0))
PRESSURE = os.environ.get("PRESSURE", "pcg")
GRAPHAMG = int(os.environ.get("GRAPHAMG", 0))
VSWEEPS = int(os.environ.get("VSWEEPS", 20))
VTOL = float(os.environ.get("VTOL", 1e-2))
MEANSCOPE = os.environ.get("MEANSCOPE", "fine")
PMAXIT = int(os.environ.get("PMAXIT", 200))
PRTOL = float(os.environ.get("PRTOL", 1e-5))
MGLEVELS = int(os.environ.get("MGLEVELS", 5))
WARMSTART = int(os.environ.get("WARMSTART", 1))
CHECK = int(os.environ.get("CHECK", 0))
OUT = os.environ.get("OUT", f"tgv_bench_np{NP}.json")
LABEL = os.environ.get("LABEL", "")

U0 = 1.0
nu = U0 * TILE / RE
dt = CFL * 1.0 / U0  # dx = 1 (grid units)
if CHECK:  # Stokes regime: advection negligible, diffusion number nu*dt sane for the smoother
    U0, nu, dt = 0.01, 0.5, 0.2
k = 2.0 * np.pi / TILE  # one TGV vortex per TILE^3; fields tile periodically

from peclet import flow  # noqa: E402

assert getattr(flow, "has_mpi", False), "flow was NOT built with PECLET_FLOW_MPI=ON"
origin, size = flow.mpi_block(GNX, GNY, GNZ)
ox, oy, oz = origin
lnx, lny, lnz = size

p0(
    f"[cfg] global {GNX}x{GNY}x{GNZ} = {GNX * GNY * GNZ / 1e6:.1f}M cells  tile={TILE}  "
    f"Re={RE:g} nu={nu:.4g} dt={dt:g}  ranks={NP}  backend={flow.execution_space}  "
    f"pressure={PRESSURE}(maxit={PMAXIT},rtol={PRTOL:g},levels={MGLEVELS},warmstart={WARMSTART})  "
    f"adv={'SOU' if ADV == 0 else 'Koren'}  steps={WARMUP}+{NSTEPS}"
)

# Per-rank block map + physical GPU (PCI bus): the decomposition record for the study, and the
# oversubscription guard (two ranks on one host+bus = shared GPU = wrecked scaling).
_bus = "-"
if flow.execution_space == "Cuda":
    try:
        import cupy as cp

        _bus = cp.cuda.runtime.deviceGetPCIBusId(cp.cuda.runtime.getDevice())
    except Exception as e:  # cupy missing is fine -- report unknown, keep running
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

# ---- Taylor-Green IC on this rank's block (global coordinates -> tiles align across ranks) ----
x = (np.arange(ox, ox + lnx) + 0.5)[:, None, None]
y = (np.arange(oy, oy + lny) + 0.5)[None, :, None]
z = (np.arange(oz, oz + lnz) + 0.5)[None, None, :]
u0 = np.asfortranarray(U0 * np.sin(k * x) * np.cos(k * y) * np.cos(k * z) * np.ones_like(z))
v0 = np.asfortranarray(-U0 * np.cos(k * x) * np.sin(k * y) * np.cos(k * z) * np.ones_like(z))
w0 = np.asfortranarray(np.zeros((lnx, lny, lnz)))

s = flow.Solver(lnx, lny, lnz)
s.init_mpi(GNX, GNY, GNZ)
s.set_rho(1.0)
s.set_mu(nu)
s.set_dt(dt)
s.set_advection(True)
s.set_advection_scheme(ADV)
s.set_velocity_solver_params(VSWEEPS, VTOL)
s.set_pressure_multigrid(True, MGLEVELS)
if PRESSURE == "pcg":
    s.set_pressure_pcg(True, PMAXIT, PRTOL)
elif PRESSURE == "cheb":
    s.set_pressure_chebyshev(True, PMAXIT, PRTOL)
elif PRESSURE != "vcycle":
    raise SystemExit(f"unknown PRESSURE={PRESSURE!r} (pcg|cheb|vcycle)")
if WARMSTART:
    s.set_pressure_warmstart(True)
if GRAPHAMG:
    s.set_pressure_graph_amg(True)  # takes effect at the geometry call below
s.set_pressure_mean_removal(MEANSCOPE)
# all-fluid cut-cell pressure operator (no solids): the production projection path, all-periodic
s.set_pressure_geometry(np.asfortranarray(np.full((lnx, lny, lnz), 1e30)))
s.set_state(u0, v0, w0)

ke0 = world.allreduce(float(np.sum(u0 * u0 + v0 * v0 + w0 * w0)), op=MPI.SUM)

# ---- warmup, then measure ---------------------------------------------------------------------
# Heartbeat: a hung distributed run (e.g. one OOM-killed rank, survivors blocked in a collective)
# is diagnosable only if the log shows how far it got.
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
    acc.setdefault("momentum_sweeps", []).append(t["momentum_sweeps"])
    iters.append(s.last_pressure_iterations())
t1 = time.perf_counter()
wall = world.allreduce(t1 - t0, op=MPI.MAX)

# Per-phase: mean over measured steps on this rank, then max/min over ranks (imbalance indicator).
stats = {}
for key, v in acc.items():
    m = float(np.mean(v))
    stats[key] = {
        "max": world.allreduce(m, op=MPI.MAX),
        "min": world.allreduce(m, op=MPI.MIN),
    }
it_mean = float(np.mean(iters))

cells = GNX * GNY * GNZ
ms_step = 1e3 * wall / NSTEPS
mcells = cells * NSTEPS / wall / 1e6
p0(f"[result] {ms_step:.1f} ms/step  {mcells:.1f} Mcell/s  pressure iters/step {it_mean:.1f}")
p0(
    "[phases, rank-max ms/step] "
    + "  ".join(f"{p}={1e3 * stats[p]['max']:.1f}" for p in phases)
    + f"  allreduce_count={stats['pressure_allreduce_count']['max']:.0f}"
)

# ---- optional analytic check: Stokes-regime TGV decay -----------------------------------------
# The TGV IC is a Stokes eigenfunction (each component: Lap u = -3 k^2 u, div u = 0, p = 0), so
# backward-Euler diffusion contracts it by exactly 1/(1 + 3 nu k^2 dt) per step and the KE must
# track (1 + 3 nu k^2 dt)^(-2 n) up to advection contamination (U0=0.01 -> negligible) and the
# iterative-solver tolerance.
check = None
if CHECK:
    u, v, w = s.get_u(), s.get_v(), s.get_w()
    ke = world.allreduce(float(np.sum(u * u + v * v + w * w)), op=MPI.SUM)
    nsteps_tot = WARMUP + NSTEPS
    ratio_num = ke / ke0
    ratio_ana = float((1.0 + 3.0 * nu * k * k * dt) ** (-2 * nsteps_tot))
    rel = abs(ratio_num - ratio_ana) / ratio_ana
    check = {"ke_ratio_measured": ratio_num, "ke_ratio_be": ratio_ana, "rel_err": rel}
    p0(f"[check] KE ratio measured {ratio_num:.6e} vs backward-Euler {ratio_ana:.6e}  rel err {rel:.2e}")

if RANK == 0:
    out = {
        "label": LABEL,
        "np": NP,
        "backend": flow.execution_space,
        "omp_threads": os.environ.get("OMP_NUM_THREADS", ""),
        "global": [GNX, GNY, GNZ],
        "cells": cells,
        "tile": TILE,
        "re": RE,
        "cfl": CFL,
        "adv": ADV,
        "pressure": PRESSURE,
        "graphamg": GRAPHAMG,
        "vsweeps": VSWEEPS,
        "vtol": VTOL,
        "meanscope": MEANSCOPE,
        "momentum_sweeps_per_step": float(np.mean(acc["momentum_sweeps"]))
        if acc.get("momentum_sweeps") else None,
        "pmaxit": PMAXIT,
        "prtol": PRTOL,
        "mglevels": MGLEVELS,
        "warmstart": WARMSTART,
        "nsteps": NSTEPS,
        "warmup": WARMUP,
        "ms_per_step": ms_step,
        "mcells_per_s": mcells,
        "pressure_iters_per_step": it_mean,
        "phase_seconds_per_step": stats,
        "blocks": [
            {"rank": rr, "host": hh, "gpu": bb, "origin": list(oo), "size": list(ss)}
            for rr, hh, bb, oo, ss in _blocks
        ],
        "check": check,
        "gpu_aware_env": os.environ.get("PECLET_CORE_GPU_AWARE_MPI", ""),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[out] {OUT}", flush=True)

world.Barrier()
MPI.Finalize()  # proper MPI shutdown (mpirun reports success) ...
os._exit(0)  # ... but skip Kokkos-finalize teardown abort (known CUDA atexit issue)
