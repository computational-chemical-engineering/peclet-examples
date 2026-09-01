#!/bin/bash
# ==========================================================================================
# FoxBerry-comparison STRONG scaling on Snellius genoa (192 cores/node): 400^3 = 64M cells,
# pure-MPI ranks = "processors" on the FoxBerry graph axis. Each job runs BOTH cases
# (single-phase + packed bed) at ONE rank count.
#
# Argument 1 = MPI rank count (the FoxBerry ladder: 24 48 96 192 384 768 1536).
# Argument 2 = optional result tag (REQUIRED after any solver change: existing JSONs are
#              skipped). Arguments, not env -- SURF sbatch drops leading env vars.
#
#   sbatch --nodes=1 foxberry_genoa.sh 24 "" single      # arg3 = case list
#   sbatch --nodes=1 foxberry_genoa.sh 48
#   sbatch --nodes=1 foxberry_genoa.sh 96
#   sbatch --nodes=1 foxberry_genoa.sh 192
#   sbatch --nodes=2 foxberry_genoa.sh 384
#   sbatch --nodes=4 foxberry_genoa.sh 768
#   sbatch --nodes=8 foxberry_genoa.sh 1536
#
# Env overrides (export BEFORE sbatch, or --export=ALL,VAR=...): SUITE BUILD VENV CASES
# ==========================================================================================
#SBATCH --job-name=fb-genoa
#SBATCH --partition=genoa
#SBATCH --nodes=1
#SBATCH --exclusive
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
PACK="$EXDIR/../results/packing_foxberry_n5000_phi0.45_s0.npz"
[ -f "$PACK" ] || { echo "FATAL: bed not found: $PACK (git pull peclet-examples)"; exit 1; }

NPROC="${1:?usage: sbatch --nodes=N foxberry_genoa.sh <ranks> [tag]}"
TAG="${2:+_${2}}"
MAXP=$(( SLURM_NNODES * 192 ))
[ "$NPROC" -le "$MAXP" ] || { echo "FATAL: $NPROC ranks need $(( (NPROC+191)/192 )) genoa nodes, allocated $SLURM_NNODES" >&2; exit 1; }
RPN=$(( (NPROC + SLURM_NNODES - 1) / SLURM_NNODES ))

export OMP_NUM_THREADS=1 OMP_PROC_BIND=false
# NSTEPS/WARMUP are overridable (--export=ALL,NSTEPS=20): the low rungs would otherwise blow
# the walltime -- 24 ranks is ~8x the 192-rank step time, i.e. ~5 h for 100 steps. The per-step
# cost is stationary (pressure iters flat 153-161 over steps 10-80 at np=192), so a shorter
# measured window is a cheaper draw of the same number, not a different measurement.
export PACK GN=400 NSTEPS="${NSTEPS:-100}" WARMUP="${WARMUP:-2}"

run_one () {  # case out
  local case=$1 out=$2
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  echo "======= $case : 400^3, $NPROC ranks x 1 thread  ($out) ======="
  env CASE=$case LABEL="snellius-genoa" OUT="$RES/$out" \
    srun --mpi=pmix --ntasks=$NPROC --ntasks-per-node=$RPN --cpus-per-task=1 \
    --distribution=block:block --cpu-bind=cores \
    "$VENV/bin/python" "$EXDIR/../foxberry_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(cfg|sdf|perf|sanity)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED $out] (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|assert|FATAL" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

# Argument 3 = which cases to run. It is an ARGUMENT, not an env var: SURF's sbatch drops
# leading `VAR=x sbatch ...` env vars, and a dropped CASES silently runs the default set
# (measured 2026-09-01: `CASES=single sbatch ...` launched the packed case instead).
for case in ${3:-${CASES:-packed single}}; do
  run_one "$case" "fb_${case}_np${NPROC}${TAG}.json"
done
echo "done -> $RES"
