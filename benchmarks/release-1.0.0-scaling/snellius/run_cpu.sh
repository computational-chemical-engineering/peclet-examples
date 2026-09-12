#!/bin/bash
# ==========================================================================================
# One rung of the CPU strong-scaling ladder on Snellius genoa (192 cores/node), peclet 1.0.0.
# One MPI rank per core, EXCLUSIVE nodes at every rung (no shared-node interference).
#
#   sbatch --nodes=1 run_cpu.sh strong bed 24
#   sbatch --nodes=1 run_cpu.sh strong bed 192
#   sbatch --nodes=8 run_cpu.sh strong bed 1536 rerun
#
# The sub-node rungs (24, 48, 96) have up to 8x the memory bandwidth per rank of the full-node
# rungs. That FLATTERS the baseline and therefore UNDERSTATES the efficiencies computed against
# it; the apples-to-apples segment is 192 -> 1536 (1, 2, 4, 8 full nodes).
#
#   $1 mode (strong|weak)   $2 case (bed|tgv)   $3 ranks   $4 optional result tag
# ==========================================================================================
#SBATCH --job-name=pec-cpu
#SBATCH --partition=genoa
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=pec-cpu-%j.out
#SBATCH --account=tes24005
set -uo pipefail

find_dir() { local c; for c in "${BENCH:-}" "${SLURM_SUBMIT_DIR:-$PWD}" "${SLURM_SUBMIT_DIR:-$PWD}/.." \
    "/projects/0/prjs1022/peclet/bench-1.0.0"; do
    [ -f "$c/scaling_bench.py" ] && { (cd "$c" && pwd); return 0; }; done
  echo "FATAL: scaling_bench.py not found (set BENCH=<campaign dir>)" >&2; exit 1; }
BENCH="$(find_dir)"
source "$BENCH/snellius/snellius_env.sh"

TAG_VERSION="${TAG_VERSION:-v1.0.0}"
PROJ="${PROJ:-/projects/0/prjs1022/peclet}"
VENV="${VENV:-$PROJ/suite-$TAG_VERSION-bench-cpu/.venv}"
source "$VENV/bin/activate"

MODE="${1:?usage: run_cpu.sh <strong|weak> <bed|tgv> <nranks> [tag]}"
CASE="${2:?}"
N="${3:?}"
TAG="${4:+_$4}"
MAXN=$(( ${SLURM_NNODES:-1} * 192 ))
[ "$N" -le "$MAXN" ] || { echo "FATAL: N=$N ranks > allocated $MAXN cores"; exit 1; }

RES="$BENCH/results/snellius-genoa"; mkdir -p "$RES"
OUT="$RES/${CASE}_${MODE}_cpu${N}${TAG}.json"
[ -f "$OUT" ] && { echo "[skip] $OUT exists"; exit 0; }

export OMP_NUM_THREADS=1 OMP_PROC_BIND=false    # one rank per core: no nested threading

echo "===== $CASE $MODE, $N ranks, ${SLURM_NNODES:-1} node(s) -> $(basename "$OUT")"
env CASE="$CASE" MODE="$MODE" \
    GPR="${GPR:-384}" GN="${GN:-384}" \
    PACK="${PACK:-$BENCH/bed_phi0.45_r18_s0.npz}" \
    NSTEPS="${NSTEPS:-20}" WARMUP="${WARMUP:-3}" \
    MARCH_TOL="${MARCH_TOL:-0}" MARCH_MAX="${MARCH_MAX:-600}" \
    LEVELS="${LEVELS:-10}" LABEL="snellius-genoa${TAG}" OUT="$OUT" \
  srun --mpi=pmix --ntasks="$N" --cpus-per-task=1 \
    "$VENV/bin/python" "$BENCH/scaling_bench.py" > "${OUT%.json}.log" 2>&1
rc=$?
grep -E "^\[(cfg|sdf|perf|phys|out)" "${OUT%.json}.log" || true
if [ $rc -ne 0 ]; then
  echo "  [FAILED rc=$rc] ${OUT%.json}.log:"
  grep -m1 -A8 "Traceback" "${OUT%.json}.log" | sed 's/^/    /'
  grep -m3 -iE "error|out of memory|assert|FATAL|Aborted" "${OUT%.json}.log" | sed 's/^/    /'
fi
exit $rc
