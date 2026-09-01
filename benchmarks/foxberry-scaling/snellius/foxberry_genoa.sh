#!/bin/bash
# ==========================================================================================
# FoxBerry-comparison STRONG scaling on Snellius genoa (192 cores/node), default grid 384^3
# (= 2^7*3, 56.6M cells -- see ../README.md for why not 401^3). Pure-MPI ranks are the
# "processors" of the FoxBerry graph axis. One job = one rank count, all requested configs.
#
# Argument 1 = MPI rank count (the FoxBerry ladder: 24 48 96 192 384 768 1536).
# Argument 2 = result tag, "" for none (REQUIRED after any solver change: existing JSONs are
#              skipped, so an untagged rerun silently reports the stale numbers).
# Argument 3 = config list, default "single packed-periodic" (see the CONFIG note below).
# All three are ARGUMENTS, not env vars -- SURF sbatch drops leading `VAR=x sbatch ...`.
#
#   sbatch --nodes=1 --time=03:00:00 --export=ALL,NSTEPS=20 foxberry_genoa.sh 24 "" "single packed-periodic"
#   sbatch --nodes=1 foxberry_genoa.sh 192
#   sbatch --nodes=2 foxberry_genoa.sh 384
#   sbatch --nodes=4 foxberry_genoa.sh 768
#   sbatch --nodes=8 foxberry_genoa.sh 1536
#   sbatch --nodes=1 --export=ALL,GN=400 foxberry_genoa.sh 192   # the 400^3 series
#
# Env overrides (via --export=ALL,VAR=...): GN NSTEPS WARMUP SUITE BUILD VENV
# ==========================================================================================
#SBATCH --job-name=fb-genoa
#SBATCH --partition=genoa
#SBATCH --nodes=1
#SBATCH --exclusive
# --exclusive alone does NOT give the node's memory: SLURM still caps the job at
# ~1792 MiB x ntasks, so a 24-rank job gets ~43 GB of genoa's 336 GB and OOM-kills at 64M
# cells (measured 2026-09-01, job 26280702, "Detected 2 oom_kill events"). --mem=0 = all of it.
#SBATCH --mem=0
#SBATCH --time=02:00:00
#SBATCH --output=fb-genoa-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
module purge; module load 2024 gompi/2024a
module load Python/3.12.3-GCCcore-13.3.0 2>/dev/null || true

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/fb/flow/build_omp_mpi}"   # pinned benchmark worktree pair (fb/flow + fb/core)
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
RES="$EXDIR/results/snellius-genoa"; mkdir -p "$RES"
BEDS="$EXDIR/../results"

NPROC="${1:?usage: sbatch --nodes=N foxberry_genoa.sh <ranks> [tag] [configs]}"
TAG="${2:+_${2}}"
MAXP=$(( SLURM_NNODES * 192 ))
[ "$NPROC" -le "$MAXP" ] || { echo "FATAL: $NPROC ranks need $(( (NPROC+191)/192 )) genoa nodes, allocated $SLURM_NNODES" >&2; exit 1; }
RPN=$(( (NPROC + SLURM_NNODES - 1) / SLURM_NNODES ))

export OMP_NUM_THREADS=1 OMP_PROC_BIND=false
# NSTEPS/WARMUP are overridable (--export=ALL,NSTEPS=20): the low rungs would otherwise blow
# the walltime -- 24 ranks is ~8x the 192-rank step time, i.e. ~5 h for 100 steps. The per-step
# cost is stationary (pressure iters flat 153-161 over steps 10-80 at np=192), so a shorter
# measured window is a cheaper draw of the same number, not a different measurement.
# GN is overridable too: 384 (= 2^7*3) is the MG-friendly grid, 400 the FoxBerry-cell-count one.
export GN="${GN:-384}" NSTEPS="${NSTEPS:-100}" WARMUP="${WARMUP:-2}"

# A CONFIG names a (case, BC mode, bed) triple, because those three are not independent:
#   single           FoxBerry Case 2 -- inlet/outlet/4 walls, no solid
#   packed           FoxBerry Case 3 -- inlet/outlet/4 walls + the y/z-periodic (x-clipped) bed
#                    *** BLOCKED: see the "Open issue" in ../README.md. Do not report. ***
#   packed-periodic  the packed bed at the same cost, fully periodic + body-force driven, on the
#                    TRIPLY-periodic bed (a y/z-only bed under periodic BCs has a broken seam)
run_one () {  # config out
  local cfg=$1 out=$2 case bc pack
  case "$cfg" in
    single)          case=single; bc=foxberry; pack="" ;;
    packed)          case=packed; bc=foxberry; pack="$BEDS/packing_foxberry_walls_n5000_phi0.45_s0.npz" ;;
    packed-periodic) case=packed; bc=periodic; pack="$BEDS/packing_foxberry_periodic_n5000_phi0.45_s0.npz" ;;
    *) echo "  [FATAL] unknown config '$cfg' (single|packed|packed-periodic)"; return 1 ;;
  esac
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  if [ -n "$pack" ] && [ ! -f "$pack" ]; then
    echo "  [FATAL] bed not found: $pack (git pull peclet-examples)"; return 1
  fi
  echo "======= $cfg : ${GN}^3, $NPROC ranks x 1 thread  ($out) ======="
  env CASE=$case BCMODE=$bc PACK="$pack" LABEL="snellius-genoa" OUT="$RES/$out" \
    srun --mpi=pmix --ntasks=$NPROC --ntasks-per-node=$RPN --cpus-per-task=1 \
    --distribution=block:block --cpu-bind=cores \
    "$VENV/bin/python" "$EXDIR/../foxberry_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(cfg|sdf|perf|sanity)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED $out] (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|assert|FATAL" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

# Argument 3 = which configs to run. It is an ARGUMENT, not an env var: SURF's sbatch drops
# leading `VAR=x sbatch ...` env vars, and a dropped CASES silently runs the default set
# (measured 2026-09-01: `CASES=single sbatch ...` launched the packed case instead).
for cfg in ${3:-${CASES:-single packed-periodic}}; do
  run_one "$cfg" "fb_${cfg}_g${GN}_np${NPROC}${TAG}.json"
done
echo "done -> $RES"
