#!/usr/bin/env python
"""Parallel scaling driver for peclet.flow 1.0.0 — one case family, four ladders, one JSON schema.

The measured problem is **creeping flow through a periodic random sphere packing with the cut-cell
immersed boundary method**, driven by a body force in a triply periodic box. One unit cell of the
packing is the physical unit of the study:

  * **strong ladders** hold ONE unit cell at a fixed grid and add ranks (`MODE=strong`);
  * the **weak ladder** gives every rank its own unit cell and tiles them (`MODE=weak`), so rung N
    is the same turbulence-free porous problem repeated N times.

Because the tiled domain is an exact periodic replication of the unit cell, the permeability is the
SAME physical number at every rung of every ladder — the study's single correctness gate. It is not
a statistical agreement across independently packed beds: it is one number, reproduced.

`CASE=tgv` runs a Taylor-Green vortex field on the identical grids with no geometry, as the control
that separates the solver floor from what the immersed boundary costs.

Everything is in PHYSICAL units (peclet 1.0.0 takes a physical domain; the cell size is derived and
never written by the user). The sphere radius R = 1 sets the length scale.

Configuration is the SHIPPED DEFAULT of 1.0.0 — MG-PCG at rtol 1e-8, coarse-level telescoping,
the 'auto' agglomerated bottom, the velocity-multigrid auto rule, the coupled momentum tolerance —
with ONE stated exception: the pressure multigrid depth is requested as deep as the grid admits
(`LEVELS`, default 10, which the solver clamps to the achievable depth) rather than the shipped
default of 4. Depth is a property of the grid, not a tuning constant; `LEVELS=4` reproduces the
out-of-the-box configuration and is reported as a sensitivity point.

Launch (one rank per GPU):
    PACK=bed.npz srun --mpi=pmix --gpus-per-task=1 --gpu-bind=per_task:1 python scaling_bench.py

Env:
    CASE        bed (default) | tgv
    MODE        strong (default) | weak
    GN          MODE=strong: global cube edge in cells (default 384)
    GPR         MODE=weak:   cells per rank per axis (default 384); global = GPR * tiles
    PACK        unit-cell packing npz from make_bed.py (required for CASE=bed)
    TILE        CASE=tgv: cells per Taylor-Green vortex (default 64)
    NSTEPS      timed steps (default 10). Every rung of every ladder must use the SAME
                WARMUP+NSTEPS, or the <u> equivalence gate below is comparing different states.
    WARMUP      untimed steps before them (default 3)
    MARCH_TOL   phase B: relative steady tolerance on <u> (default 0 = SKIP the march; the
                permeability is a property of the unit cell, so it is measured at a few rungs,
                not at every one -- the per-rung gate is the free <u> equivalence below)
    MARCH_MAX   phase B step cap (default 600)
    DIFFNUM     diffusion number mu*dt/(rho*h^2) that sets dt (default 6.0)
    LEVELS      pressure MG depth requested (default 10 -> clamped to what the grid admits)
    VMG         momentum solver, PINNED across the ladder instead of left to the 1.0.0 auto
                rule (which switches below 65536 cells/rank, so only the top rung of a strong
                ladder crosses it and the ladder changes ALGORITHM there):
                  auto  the shipped rule (default)
                  off   red-black Gauss-Seidel at every rank count
                  on    velocity V-cycle at every rank count
                  cheb  Chebyshev semi-iteration at every rank count
                  mgcheb  velocity V-cycle with a Chebyshev smoother on every level
    CHEB_MAXIT  VMG=cheb: iteration cap per component (default 400)
    MGCHEB_DEGREE / MGCHEB_RATIO
                VMG=mgcheb: polynomial degree (0 = follow the V-cycle's pre/post/bottom
                sweep counts) and the spectral interval ratio [hi/ratio, hi] (default 10)
    VMG_LEVELS  VMG=on: velocity-MG depth (default 3 = what the auto rule selects)
    VMG_VCYCLES VMG=on: V-cycle cap per component (default 40 = what the auto rule selects)
    MU F RHO    viscosity / body force / density (default 0.1 / 1e-3 / 1.0)
    OUT LABEL   output JSON path / free-form label
"""
import json
import os
import socket
import time

import numpy as np
from mpi4py import MPI

world = MPI.COMM_WORLD
RANK, NP = world.rank, world.size


def p0(*a):
    if RANK == 0:
        print(*a, flush=True)


CASE = os.environ.get("CASE", "bed")
MODE = os.environ.get("MODE", "strong")
GN = int(os.environ.get("GN", 384))
GPR = int(os.environ.get("GPR", 384))
PACK = os.environ.get("PACK", "")
TILE = int(os.environ.get("TILE", 64))
NSTEPS = int(os.environ.get("NSTEPS", 10))
WARMUP = int(os.environ.get("WARMUP", 3))
MARCH_TOL = float(os.environ.get("MARCH_TOL", 0.0))
MARCH_MAX = int(os.environ.get("MARCH_MAX", 600))
DIFFNUM = float(os.environ.get("DIFFNUM", 6.0))
LEVELS = int(os.environ.get("LEVELS", 10))
VMG = os.environ.get("VMG", "auto").lower()
if VMG not in ("auto", "off", "on", "cheb", "mgcheb"):
    raise SystemExit(f"VMG must be auto|off|on|cheb|mgcheb, got {VMG!r}")
VMG_LEVELS = int(os.environ.get("VMG_LEVELS", 3))
VMG_VCYCLES = int(os.environ.get("VMG_VCYCLES", 40))
CHEB_MAXIT = int(os.environ.get("CHEB_MAXIT", 400))
MGCHEB_DEGREE = int(os.environ.get("MGCHEB_DEGREE", 0))
MGCHEB_RATIO = float(os.environ.get("MGCHEB_RATIO", 10.0))
MU = float(os.environ.get("MU", 0.1))
F = float(os.environ.get("F", 1e-3))
RHO = float(os.environ.get("RHO", 1.0))
OUT = os.environ.get("OUT", f"scaling_{CASE}_{MODE}_np{NP}.json")
LABEL = os.environ.get("LABEL", "")

if CASE not in ("bed", "tgv"):
    raise SystemExit(f"CASE={CASE!r} (bed|tgv)")
if MODE not in ("strong", "weak"):
    raise SystemExit(f"MODE={MODE!r} (strong|weak)")


def tile_factors(n):
    """Split n ranks into (tx, ty, tz) by doubling x, y, z in turn — the most cubic tiling, and the
    order an ORB bisection of the resulting box follows, so every rank owns exactly one tile."""
    if n & (n - 1):
        raise SystemExit(f"MODE=weak needs a power-of-two rank count, got {n}")
    t = [1, 1, 1]
    ax = 0
    while t[0] * t[1] * t[2] < n:
        t[ax] *= 2
        ax = (ax + 1) % 3
    return tuple(t)


# ---- geometry unit cell -------------------------------------------------------------------------
if CASE == "bed":
    if not PACK:
        raise SystemExit("PACK=<unit-cell packing npz from make_bed.py> is required for CASE=bed")
    pk = np.load(PACK)
    centers, scales, box = pk["centers"], pk["scales"], pk["box"]
    if not np.allclose(box, box[0], rtol=1e-12):
        raise SystemExit(f"the unit cell must be cubic to tile isotropically, got box={box}")
    L_UNIT = float(box[0])              # unit-cell side, in sphere radii (R = 1)
    PHI_PACK = float(pk["phi"])
else:
    L_UNIT = None                        # set below from the vortex count
    PHI_PACK = 0.0

# ---- grid, tiling, physical domain ---------------------------------------------------------------
if MODE == "weak":
    TILES = tile_factors(NP)
    G = np.array([GPR * TILES[0], GPR * TILES[1], GPR * TILES[2]], dtype=np.int64)
    CELLS_UNIT = GPR
else:
    TILES = (1, 1, 1)
    G = np.array([GN, GN, GN], dtype=np.int64)
    CELLS_UNIT = GN

if CASE == "tgv":
    if CELLS_UNIT % TILE:
        raise SystemExit(f"TILE={TILE} must divide the per-unit-cell edge {CELLS_UNIT}")
    L_UNIT = 2.0 * np.pi * (CELLS_UNIT // TILE)   # one 2*pi vortex per TILE cells

GNX, GNY, GNZ = (int(v) for v in G)
EXTENT = (L_UNIT * TILES[0], L_UNIT * TILES[1], L_UNIT * TILES[2])
H = L_UNIT / CELLS_UNIT                  # cell size, physical (isotropic by construction)
RCELLS = 1.0 / H                          # sphere radius in cells (R = 1 physical)
DT = DIFFNUM * RHO * H * H / MU

from peclet import flow  # noqa: E402

assert getattr(flow, "has_mpi", False), "flow was NOT built with PECLET_FLOW_MPI=ON"
origin, size = flow.mpi_block(GNX, GNY, GNZ)
ox, oy, oz = (int(v) for v in origin)
lnx, lny, lnz = (int(v) for v in size)

p0(f"[cfg] case={CASE} mode={MODE} ranks={NP} tiles={TILES}  global {GNX}x{GNY}x{GNZ} = "
   f"{GNX * GNY * GNZ / 1e6:.1f}M cells ({GNX * GNY * GNZ / float(NP) / 1e6:.1f}M/rank)")
_geo = f"R={RCELLS:.2f} cells" if CASE == "bed" else f"{TILE} cells/vortex"
p0(f"[cfg] extent={EXTENT[0]:.4f}x{EXTENT[1]:.4f}x{EXTENT[2]:.4f}  h={H:.6f}  {_geo}  "
   f"dt={DT:.6g} (diffusion number {DIFFNUM:g})  "
   f"rho={RHO:g} mu={MU:g} F={F:g}  levels_requested={LEVELS}  vmg={VMG}")
_march = f"march(tol={MARCH_TOL:g}, max={MARCH_MAX})" if CASE == "bed" else "no march (tgv)"
p0(f"[cfg] flow {flow.__version__}  backend={flow.execution_space}  steps={WARMUP}+{NSTEPS}  "
   f"{_march}  label={LABEL!r}")

# Per-rank block map + physical GPU: the decomposition record, and the oversubscription guard
# (two ranks on one host+bus = a shared GPU = a wrecked scaling curve that looks like a solver
# problem). Cheap, and it has caught a misconfigured launch before.
_bus = "-"
if flow.execution_space == "Cuda":
    try:
        import cupy as cp

        _bus = cp.cuda.runtime.deviceGetPCIBusId(cp.cuda.runtime.getDevice())
    except Exception as e:
        _bus = f"<unknown:{type(e).__name__}>"
_blocks = world.gather((RANK, socket.gethostname(), _bus, (ox, oy, oz), (lnx, lny, lnz)), root=0)
BLOCK_UNIFORM = None
if RANK == 0:
    seen = {}
    sizes = set()
    for rr, hh, bb, oo, ss in _blocks:
        seen.setdefault((hh, bb), []).append(rr)
        sizes.add(tuple(ss))
    BLOCK_UNIFORM = len(sizes) == 1
    print(f"  blocks: {len(sizes)} distinct shape(s) {sorted(sizes)[:4]}"
          f"{' ...' if len(sizes) > 4 else ''}  hosts={len({h for _, h, _, _, _ in _blocks})}",
          flush=True)
    dups = {k: v for k, v in seen.items() if len(v) > 1 and flow.execution_space == "Cuda"}
    if dups:
        print(f"  WARNING: GPUs shared by >1 rank (oversubscription): {dups}", flush=True)
BLOCK_UNIFORM = world.bcast(BLOCK_UNIFORM, root=0)

# ---- rank-local geometry --------------------------------------------------------------------
# Physical cell centres of THIS rank's block; the SDF is sampled rank-locally and never gathered.
xc = (ox + np.arange(lnx) + 0.5) * H
yc = (oy + np.arange(lny) + 0.5) * H
zc = (oz + np.arange(lnz) + 0.5) * H

t_geo0 = time.perf_counter()
phi_vox = 0.0
if CASE == "bed":
    # Sphere centres of every tile, then the 26 periodic images of the whole domain. Only spheres
    # whose support reaches this block are visited, so the cost is set by the block, not the domain.
    tiled = np.concatenate([centers + np.array([i, j, k], np.float64) * L_UNIT
                            for i in range(TILES[0])
                            for j in range(TILES[1])
                            for k in range(TILES[2])])
    radii = np.tile(scales, TILES[0] * TILES[1] * TILES[2])
    BAND = 4.0 * H                     # accurate SDF band beyond the surface, 4 cells
    sdf = np.full((lnx, lny, lnz), 1e30, order="F")
    blk_lo = np.array([xc[0], yc[0], zc[0]]) - 0.5 * H
    blk_hi = np.array([xc[-1], yc[-1], zc[-1]]) + 0.5 * H
    E = np.array(EXTENT)
    shifts = np.stack(np.meshgrid([-1, 0, 1], [-1, 0, 1], [-1, 0, 1], indexing="ij"), -1)
    for sh in shifts.reshape(-1, 3) * E:
        cs = tiled + sh
        reach = radii + BAND
        m = np.all((cs + reach[:, None] > blk_lo) & (cs - reach[:, None] < blk_hi), axis=1)
        for cx, cy, cz, rr in zip(cs[m, 0], cs[m, 1], cs[m, 2], radii[m]):
            i0, i1 = np.searchsorted(xc, [cx - rr - BAND, cx + rr + BAND])
            j0, j1 = np.searchsorted(yc, [cy - rr - BAND, cy + rr + BAND])
            k0, k1 = np.searchsorted(zc, [cz - rr - BAND, cz + rr + BAND])
            if i0 >= i1 or j0 >= j1 or k0 >= k1:
                continue
            d = np.sqrt((xc[i0:i1, None, None] - cx) ** 2
                        + (yc[None, j0:j1, None] - cy) ** 2
                        + (zc[None, None, k0:k1] - cz) ** 2) - rr
            np.minimum(sdf[i0:i1, j0:j1, k0:k1], d, out=sdf[i0:i1, j0:j1, k0:k1])
    sdf = np.asfortranarray(np.clip(sdf, -1e3, 1e3))
    nsolid = world.allreduce(int((sdf < 0).sum()), op=MPI.SUM)
    phi_vox = nsolid / float(GNX) / float(GNY) / float(GNZ)
    p0(f"[sdf] built in {time.perf_counter() - t_geo0:.1f}s  voxel solid fraction={phi_vox:.4f} "
       f"(packing {PHI_PACK:.4f})")
    # Gate the ARTIFACT, not the packer's self-report: an unresolved packing (overlapping spheres)
    # has union volume < N*V_sphere, so the sampled fraction falls below the analytic phi. This has
    # fired in the field on a silently corrupted packing whose own overlap metric stayed quiet.
    if abs(phi_vox - PHI_PACK) > 0.02:
        p0(f"FATAL: voxel solid fraction {phi_vox:.4f} vs packing phi {PHI_PACK:.4f} — the bed in "
           f"{PACK} is not a converged packing. Refusing to run.")
        world.Barrier()
        raise SystemExit(1)

# ---- solver: the shipped 1.0.0 configuration, on a physical domain --------------------------
s = flow.Solver(cells=(lnx, lny, lnz), extent=EXTENT, origin=(0.0, 0.0, 0.0),
                global_cells=(GNX, GNY, GNZ))
s.init_mpi(GNX, GNY, GNZ)
s.set_rho(RHO)
s.set_mu(MU)
s.set_dt(DT)
s.set_pressure_multigrid(True, LEVELS)     # the one stated departure from the defaults
# Momentum solver, PINNED. The 1.0.0 auto rule (setSolidVelocityMgAuto) switches solver below
# 65536 cells/rank, so a strong-scaling ladder run with VMG=auto changes ALGORITHM at its top
# rung and measures two things at once. An explicit set_velocity_multigrid call sets vmgExplicit_
# and the auto rule then never fires, at any rank count.
if VMG == "off":
    s.set_velocity_multigrid(False)
elif VMG == "on":
    s.set_velocity_multigrid(True, VMG_LEVELS, VMG_VCYCLES)
elif VMG == "cheb":
    s.set_velocity_multigrid(False)          # also clears the auto rule
    s.set_velocity_chebyshev(True, CHEB_MAXIT)
elif VMG == "mgcheb":
    s.set_velocity_multigrid(True, VMG_LEVELS, VMG_VCYCLES)
    s.set_velocity_mg_chebyshev(True, MGCHEB_DEGREE, MGCHEB_RATIO)
if CASE == "bed":
    s.set_advection(False)                 # creeping flow
    s.set_body_force((F, 0.0, 0.0))
    s.set_solid(sdf, cutcell_pressure=True)
else:
    s.set_advection(True)
    kw = 2.0 * np.pi / (TILE * H)          # one vortex per TILE cells, in physical units
    U0 = 1.0
    X = xc[:, None, None]
    Y = yc[None, :, None]
    Z = zc[None, None, :]
    ones = np.ones((lnx, lny, lnz))
    u0 = np.asfortranarray(U0 * np.sin(kw * X) * np.cos(kw * Y) * np.cos(kw * Z) * ones)
    v0 = np.asfortranarray(-U0 * np.cos(kw * X) * np.sin(kw * Y) * np.cos(kw * Z) * ones)
    w0 = np.asfortranarray(np.zeros((lnx, lny, lnz)))
    # the all-fluid cut-cell pressure operator (no solid): the production projection path
    s.set_pressure_geometry(np.asfortranarray(np.full((lnx, lny, lnz), 1e30)))
    s.set_state(u0, v0, w0)

CELLS_TOTAL = float(GNX) * float(GNY) * float(GNZ)


def gmean_u():
    return world.allreduce(float(np.sum(s.get_u())), op=MPI.SUM) / CELLS_TOTAL


def gate_value():
    """The scalar the cross-rung equivalence gate compares. <u> on the bed (it is the superficial
    velocity the permeability is read from); mean kinetic energy for TGV, whose <u> vanishes by
    symmetry and would compare zero against zero."""
    if CASE == "bed":
        return gmean_u()
    ke = float(np.sum(s.get_u() ** 2) + np.sum(s.get_v() ** 2) + np.sum(s.get_w() ** 2))
    return world.allreduce(ke, op=MPI.SUM) / CELLS_TOTAL


# ---- phase A: timed steps ---------------------------------------------------------------------
for _ in range(WARMUP):
    s.step()
world.Barrier()

steps = []
for _ in range(NSTEPS):
    world.Barrier()
    t0 = time.perf_counter()
    s.step()
    tm = dict(s.diagnostics.last_step_timers())     # device-fenced: this is also the sync point
    t1 = time.perf_counter()
    rec = {"wall": world.allreduce(t1 - t0, op=MPI.MAX),
           "iters": int(s.diagnostics.last_pressure_iterations())}
    for kk in ("predictor", "momentum", "projection", "pressure_allreduce",
               "pressure_allreduce_count", "momentum_sweeps"):
        if kk in tm:
            op = MPI.SUM if kk.endswith("count") else MPI.MAX
            rec[kk] = world.allreduce(float(tm[kk]), op=op)
    steps.append(rec)

# Cross-rung equivalence gate, and it costs one allreduce: every run starts from rest and takes
# WARMUP+NSTEPS identical steps, so <u> at this point is the SAME number at every rank count and on
# both machines (the distributed step is bit-exact to single-rank up to the reduction-order floor),
# and on the weak ladder the tiled domain is an exact replication of the unit cell. A rung that
# disagrees here is wrong, whatever its timings look like.
u_after = gate_value()
div_after = float(s.max_open_divergence())
p0(f"[gate] {'<u>' if CASE == 'bed' else '<KE>'} after {WARMUP + NSTEPS} steps = "
   f"{u_after:.12e}   max|div| = {div_after:.3e}")

wall = np.array([r["wall"] for r in steps])
iters = np.array([r["iters"] for r in steps], dtype=float)
mcells_s = (CELLS_TOTAL / 1e6) / float(np.median(wall))
p0(f"[perf] {np.median(wall) * 1e3:.1f} ms/step (median)  mean {wall.mean() * 1e3:.1f}  "
   f"min {wall.min() * 1e3:.1f}  max {wall.max() * 1e3:.1f}   "
   f"{mcells_s:.1f} Mcell/s total, {mcells_s / NP:.2f} Mcell/s/rank")
p0(f"[perf] pressure iterations/step: mean {iters.mean():.1f}  max {int(iters.max())}   "
   f"levels achieved: {list(s.diagnostics.pressure_mg_level_ratios())}")

# ---- phase B: march to steady state, permeability ----------------------------------------------
phys = {}
if CASE == "bed" and MARCH_TOL > 0:
    t_m0 = time.perf_counter()
    prev = gmean_u()
    n_marched = 0
    converged = False
    while n_marched < MARCH_MAX:
        for _ in range(5):
            s.step()
        n_marched += 5
        cur = gmean_u()
        if cur != 0.0 and abs(cur - prev) / abs(cur) < MARCH_TOL:
            converged = True
            prev = cur
            break
        prev = cur
    umean = prev
    # k/R^2 with R = 1: the Darcy permeability from the superficial velocity <u> = Q/A.
    k_over_R2 = MU * umean / F
    phys = {"u_mean": umean, "k_over_R2": k_over_R2, "march_steps": n_marched,
            "march_converged": bool(converged), "march_seconds": time.perf_counter() - t_m0,
            "max_open_divergence": float(s.max_open_divergence())}
    p0(f"[phys] k/R^2 = {k_over_R2:.9e}  <u> = {umean:.9e}  after {n_marched} steps "
       f"({'converged' if converged else 'CAP HIT'})  max|div| = {phys['max_open_divergence']:.3e}")

# ---- record ------------------------------------------------------------------------------------
if RANK == 0:
    out = {
        "schema": "peclet-scaling-1",
        "label": LABEL,
        "case": CASE,
        "mode": MODE,
        "ranks": NP,
        "tiles": list(TILES),
        "grid": [GNX, GNY, GNZ],
        "cells_total": CELLS_TOTAL,
        "cells_per_rank": CELLS_TOTAL / NP,
        "extent": list(EXTENT),
        "spacing": H,
        "r_cells": RCELLS if CASE == "bed" else None,
        "cells_per_vortex": TILE if CASE == "tgv" else None,
        "phi_packing": PHI_PACK,
        "phi_voxel": phi_vox,
        "blocks_uniform": bool(BLOCK_UNIFORM),
        "pack": os.path.basename(PACK),
        "flow_version": flow.__version__,
        "backend": flow.execution_space,
        "physics": {"rho": RHO, "mu": MU, "body_force": F, "dt": DT, "diffusion_number": DIFFNUM},
        "solver": {"levels_requested": LEVELS,
                   "level_ratios": list(s.diagnostics.pressure_mg_level_ratios()),
                   "telescope": bool(s.pressure_telescope),
                   "velocity_multigrid_active": bool(s.diagnostics.velocity_multigrid_active()),
                   "vmg_pin": VMG,
                   "cheb_active": bool(getattr(s, "velocity_chebyshev_active", lambda: False)()),
                   "mgcheb_active": bool(getattr(s, "velocity_mg_chebyshev", lambda: False)()),
                   "mgcheb_degree": MGCHEB_DEGREE if VMG == "mgcheb" else None,
                   "mgcheb_ratio": MGCHEB_RATIO if VMG == "mgcheb" else None,
                   "vmg_levels": VMG_LEVELS if VMG == "on" else None,
                   "vmg_vcycles": VMG_VCYCLES if VMG == "on" else None,
                   "pressure_rtol_default": True},
        "perf": {
            "warmup": WARMUP,
            "nsteps": NSTEPS,
            "ms_per_step_median": float(np.median(wall)) * 1e3,
            "ms_per_step_mean": float(wall.mean()) * 1e3,
            "ms_per_step_min": float(wall.min()) * 1e3,
            "ms_per_step_max": float(wall.max()) * 1e3,
            "mcells_per_s": mcells_s,
            "mcells_per_s_per_rank": mcells_s / NP,
            "pressure_iters_mean": float(iters.mean()),
            "pressure_iters_max": int(iters.max()),
            "steps": steps,
        },
        "gate": {"steps": WARMUP + NSTEPS,
                 "quantity": "u_mean" if CASE == "bed" else "ke_mean", "value": u_after, "max_open_divergence": div_after},
        "physics_result": phys,
        "env": {k: v for k, v in os.environ.items()
                if k.startswith(("PECLET_", "OMP_", "SLURM_JOB", "UCX_", "OMPI_"))},
        "host": socket.gethostname(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[out] {OUT}", flush=True)
