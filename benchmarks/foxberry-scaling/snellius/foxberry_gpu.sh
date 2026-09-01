#!/bin/bash
# ==========================================================================================
# FoxBerry-comparison scaling on Snellius gpu_h100 (4x H100 94GB/node): the SAME 400^3 = 64M
# cell cases as foxberry_genoa.sh, strong-scaled over GPUs. Each job runs BOTH cases at ONE
# GPU count.
#
# Argument 1 = GPU count (1 2 4 on one node; 8 = 2 nodes; 16 = 4 nodes).
# Argument 2 = optional result tag.
#
#   sbatch --nodes=1 foxberry_gpu.sh 1
#   sbatch --nodes=1 foxberry_gpu.sh 2
#   sbatch --nodes=1 foxberry_gpu.sh 4
#   sbatch --nodes=2 foxberry_gpu.sh 8
#   sbatch --nodes=4 foxberry_gpu.sh 16
# ==========================================================================================
#SBATCH --job-name=fb-gpu
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=01:00:00
#SBATCH --output=fb-gpu-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/fb/flow/build_cuda_mpi}"  # pinned benchmark worktree pair (fb/flow + fb/core)
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI="${GPU_AWARE:-1}"
RES="$EXDIR/results/snellius-h100"; mkdir -p "$RES"
PACK="$EXDIR/../results/packing_foxberry_n5000_phi0.45_s0.npz"
[ -f "$PACK" ] || { echo "FATAL: bed not found: $PACK (git pull peclet-examples)"; exit 1; }

N="${1:?usage: sbatch --nodes=N foxberry_gpu.sh <gpus> [tag]}"
TAG="${2:+_${2}}"
MAXN=$(( SLURM_NNODES * 4 ))
[ "$N" -le "$MAXN" ] || { echo "FATAL: N=$N GPUs need $(( (N+3)/4 )) nodes, allocated $SLURM_NNODES" >&2; exit 1; }

export PACK GN=400 NSTEPS=100 WARMUP=2

run_one () {  # case out
  local case=$1 out=$2
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  echo "======= $case : 400^3, $N GPUs  ($out) ======="
  env CASE=$case LABEL="snellius-h100" OUT="$RES/$out" \
    srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXDIR/../foxberry_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(cfg|sdf|perf|sanity)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED $out] (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|out of memory|assert|FATAL" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

# Argument 3 = which cases to run (ARGUMENT, not env: SURF sbatch drops leading VAR=x).
for case in ${3:-${CASES:-packed single}}; do
  run_one "$case" "fb_${case}_gpu${N}${TAG}.json"
done
echo "done -> $RES"
