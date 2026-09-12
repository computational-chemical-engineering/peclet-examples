#!/bin/bash
# ==========================================================================================
# One rung of a GPU ladder on Snellius gpu_h100 (4x H100 94GB per node), peclet 1.0.0.
#
#   sbatch --nodes=1 --gpus-per-node=1 --ntasks-per-node=1 run_gpu.sh weak   bed 1
#   sbatch --nodes=1 --gpus-per-node=2 --ntasks-per-node=2 run_gpu.sh weak   bed 2
#   sbatch --nodes=1 --gpus-per-node=4 --ntasks-per-node=4 run_gpu.sh weak   bed 4
#   sbatch --nodes=2 --gpus-per-node=4 --ntasks-per-node=4 run_gpu.sh weak   bed 8
#   sbatch --nodes=8 --gpus-per-node=4 --ntasks-per-node=4 run_gpu.sh strong bed 32 rerun
#
# BILLING IS PER ALLOCATED GPU, not per used GPU: the 1- and 2-GPU rungs MUST override
# --gpus-per-node or they cost four. Arguments are POSITIONAL (SURF's sbatch drops VAR=x).
#
#   $1 mode (weak|strong)   $2 case (bed|tgv)   $3 GPUs   $4 optional result tag
# ==========================================================================================
#SBATCH --job-name=pec-gpu
#SBATCH --partition=gpu_h100
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=00:45:00
#SBATCH --output=pec-gpu-%j.out
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
VENV="${VENV:-$PROJ/suite-$TAG_VERSION-bench-h100/.venv}"
source "$VENV/bin/activate"

MODE="${1:?usage: run_gpu.sh <weak|strong> <bed|tgv> <ngpus> [tag]}"
CASE="${2:?}"
N="${3:?}"
TAG="${4:+_$4}"
MAXN=$(( ${SLURM_NNODES:-1} * ${SLURM_GPUS_PER_NODE:-4} ))
[ "$N" -le "$MAXN" ] || { echo "FATAL: N=$N GPUs > allocated $MAXN"; exit 1; }

RES="$BENCH/results/snellius-h100"; mkdir -p "$RES"
OUT="$RES/${CASE}_${MODE}_gpu${N}${TAG}.json"
[ -f "$OUT" ] && { echo "[skip] $OUT exists"; exit 0; }

# Host-side Kokkos is OpenMP in this prefix: an unbounded pool on a big host is a measured trap.
export OMP_NUM_THREADS=8 OMP_PROC_BIND=false
export PECLET_BIND_GPU=0            # --gpu-bind=per_task:1 already gives each rank its own device
export PECLET_CORE_HALO_VERBOSE=1   # record which MPI buffer path the default resolution chose
# PECLET_CORE_GPU_AWARE_MPI deliberately UNSET: the shipped auto-detection is what is being measured.

echo "===== $CASE $MODE, $N GPU(s), ${SLURM_NNODES:-1} node(s) -> $(basename "$OUT")"
env CASE="$CASE" MODE="$MODE" \
    GPR="${GPR:-384}" GN="${GN:-384}" \
    PACK="${PACK:-$BENCH/bed_phi0.45_r18_s0.npz}" \
    NSTEPS="${NSTEPS:-20}" WARMUP="${WARMUP:-3}" \
    MARCH_TOL="${MARCH_TOL:-0}" MARCH_MAX="${MARCH_MAX:-600}" \
    LEVELS="${LEVELS:-10}" LABEL="snellius-h100${TAG}" OUT="$OUT" \
  srun --mpi=pmix --ntasks="$N" --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$BENCH/scaling_bench.py" > "${OUT%.json}.log" 2>&1
rc=$?
grep -E "^\[(cfg|sdf|perf|phys|out)" "${OUT%.json}.log" || true
if [ $rc -ne 0 ]; then
  echo "  [FAILED rc=$rc] ${OUT%.json}.log:"
  grep -m1 -A8 "Traceback" "${OUT%.json}.log" | sed 's/^/    /'
  grep -m3 -iE "error|out of memory|assert|FATAL|Aborted" "${OUT%.json}.log" | sed 's/^/    /'
fi
exit $rc
