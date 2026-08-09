#!/usr/bin/env bash
# Run the tiled-TGV benchmark on incflo (AMReX-Fluids: FV incompressible NS, geometric-multigrid
# projections, embedded-boundary capable — the exascale reference closest to peclet's method
# family) and emit a JSON result compatible with tgv_bench.py's output.
#
# probtype=3 is incflo's 3-D Taylor-Green: IC period is 1.0 domain unit, so prob_hi = tile counts
# reproduces the same tiled field as tgv_bench.py; mu=0.01, rho=1 gives Re_tile = 100.
#
# Usage: NP=4 NX=128 NY=128 NZ=128 NSTEPS=20 OUT=incflo_np4.json ./run_incflo.sh
#
# FAIR-COMPARISON SETTINGS (measured ablation, serial 128^3: 6402 -> 4183 ms/step, 1.53x):
#   MAXGRID (default 64): AMReX default max_grid_size=32 shreds each rank into tiny boxes
#     (ghost overhead); 64 balances box count against per-box overhead at our rank counts.
#   MGRTOL (default 1e-5): AMReX MLMG defaults to ~1e-11 — far tighter than peclet (1e-5) or
#     OpenFOAM (~1e-6) pay; matched to the study's tolerance level.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
NP=${NP:-1}
NX=${NX:-64}; NY=${NY:-64}; NZ=${NZ:-64}
NSTEPS=${NSTEPS:-20}
TILE=${TILE:-64}
OUT=${OUT:-incflo_np${NP}.json}
case "$OUT" in /*) : ;; *) OUT="$PWD/$OUT" ;; esac
LABEL=${LABEL:-incflo}
INCFLO=${INCFLO:-$HOME/Codes/scaling-refs/incflo/build/incflo.ex}
MPIRUN=${MPIRUN:-/usr/bin/mpirun}
MAXGRID=${MAXGRID:-64}
MGRTOL=${MGRTOL:-1e-5}

NTX=$((NX / TILE)); NTY=$((NY / TILE)); NTZ=$((NZ / TILE))
DT=$(python3 -c "print(0.2/$TILE)")     # CFL 0.2: dx = 1/TILE domain units, U0 = 1

WORK=$(mktemp -d "${TMPDIR:-/tmp}/incflotgv.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
cat > "$WORK/inputs" <<EOF
max_step                = $NSTEPS
stop_time               = 1e9
incflo.fixed_dt         = $DT
incflo.cfl              = 0.9
incflo.verbose          = 2
amr.plot_int            = -1
amr.check_int           = -1
incflo.gravity          = 0. 0. 0.
incflo.ro_0             = 1.
incflo.mu               = 0.01
amr.n_cell              = $NX $NY $NZ
amr.max_level           = 0
amr.max_grid_size       = $MAXGRID
mac_proj.mg_rtol        = $MGRTOL
nodal_proj.mg_rtol      = $MGRTOL
diffusion.mg_rtol       = $MGRTOL
geometry.prob_lo        = 0. 0. 0.
geometry.prob_hi        = $NTX. $NTY. $NTZ.
geometry.is_periodic    = 1 1 1
incflo.probtype         = 3
EOF
# extra AMReX/incflo input lines from the caller (e.g. amrex.use_gpu_aware_mpi = 1)
[ -n "${EXTRA:-}" ] && printf '%s\n' "$EXTRA" >> "$WORK/inputs"

cd "$WORK"
$MPIRUN ${NPFLAG:--np} "$NP" ${MPIFLAGS:---bind-to core} "$INCFLO" inputs > log.run 2>&1 || {
  cp log.run "${OUT%.json}.faillog" 2>/dev/null   # durable full log next to the results
  echo "[run_incflo FAILED] full log: ${OUT%.json}.faillog; tail:" >&2
  tail -25 log.run >&2; exit 1; }

# per-step wall time from incflo's per-step "Time per step" prints; steady half
python3 - log.run "$NP" "$NX" "$NY" "$NZ" "$NSTEPS" "$LABEL" "$OUT" "$MAXGRID" "$MGRTOL" <<'EOF'
import json, re, sys
log, np_, nx, ny, nz, nsteps, label, out, maxgrid, mgrtol = sys.argv[1:]
np_, nx, ny, nz, nsteps = int(np_), int(nx), int(ny), int(nz), int(nsteps)
txt = open(log).read()
t = [float(m.group(1)) for m in re.finditer(r"Time per step (\S+)", txt)]
if len(t) < 4:
    sys.exit(f"too few per-step timings in {log} ({len(t)})")
d = t[len(t) // 2:]
ms = 1e3 * sum(d) / len(d)
cells = nx * ny * nz
res = {"label": label, "np": np_, "backend": "cpu", "global": [nx, ny, nz], "cells": cells,
       "nsteps": nsteps, "ms_per_step": ms, "mcells_per_s": cells / (ms / 1e3) / 1e6,
       "code": "incflo", "solver": "FV+MLMG-projection",
       "maxgrid": int(maxgrid), "mg_rtol": float(mgrtol)}
json.dump(res, open(out, "w"), indent=1)
print(f"[result] {ms:.1f} ms/step  {res['mcells_per_s']:.2f} Mcell/s  -> {out}")
EOF
