#!/bin/bash
# ==========================================================================================
# TGV weak scaling on Snellius gpu_h100 — 47.2M cells/GPU fixed (384x384x320 per GPU, tile 64),
# GNX grows with N. Sweeps every N that fits the allocation and has no JSON yet (resumable).
# Short runs (10+40 steps): a full sweep costs a few minutes of GPU time per point.
#
# Argument = the specific GPU count to measure (queue-parallel safe: each job touches only its
# own point), or 'levers' for the ablation at the allocated max, or empty = sweep all that fit
# (only safe when jobs run one at a time). Argument, not env var — SURF sbatch drops leading env.
#   sbatch --nodes=1 tgv_weak_gpu.sh 1
#   sbatch --nodes=1 tgv_weak_gpu.sh 2
#   sbatch --nodes=1 tgv_weak_gpu.sh 4
#   sbatch --nodes=2 tgv_weak_gpu.sh 8
#   sbatch --nodes=4 tgv_weak_gpu.sh 16
#   sbatch --nodes=8 tgv_weak_gpu.sh 32
#   sbatch --nodes=2 tgv_weak_gpu.sh levers     # cheb / mean-scope / GraphAMG / host-staged at N=8
#   sbatch --nodes=4 tgv_weak_gpu.sh levers     # same at N=16
# ==========================================================================================
#SBATCH --job-name=tgv-weak
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=00:45:00
#SBATCH --output=tgv-weak-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI="${GPU_AWARE:-1}"
RES="$EXDIR/results/snellius-h100"; mkdir -p "$RES"

export TILE=64 GNY=384 GNZ=320 NSTEPS=40 WARMUP=10 RE=100 ADV=0
BASE_GNX=384    # 384x384x320 = 47.2M cells/GPU
MAXN=$(( SLURM_NNODES * 4 ))

run_one () {  # N out extra-env...
  local N=$1 out=$2; shift 2
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  echo "======= N=$N : $((BASE_GNX * N))x${GNY}x${GNZ} = $(( BASE_GNX * N * GNY * GNZ / 1000000 ))M  ($out) ======="
  env GNX=$(( BASE_GNX * N )) LABEL="snellius-h100" OUT="$RES/$out" "$@" \
    srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXDIR/../tgv_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(result|check)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED N=$N] rank-0 error (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|out of memory|assert" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

ARG="${1:-}"
if [ -n "$ARG" ] && [ "$ARG" != levers ]; then
  [ "$ARG" -le "$MAXN" ] || { echo "FATAL: N=$ARG needs $(( (ARG+3)/4 )) nodes, allocated $SLURM_NNODES" >&2; exit 1; }
  run_one "$ARG" "weak_np${ARG}.json"
else
  for N in 1 2 4 8 16 32; do
    [ "$N" -le "$MAXN" ] && run_one $N "weak_np${N}.json"
  done
fi

# Lever ablation at the largest allocated N (inter-node points 8/16 are the interesting ones).
# The default run already uses MEANSCOPE=fine (5.4 allreduces/iter); meanall restores the legacy
# scope (17.6/iter) to quantify the reduction tax directly at scale.
if [ "$ARG" = levers ] || [ "${LEVERS:-0}" = 1 ]; then
  run_one $MAXN "weak_np${MAXN}_cheb.json"    env PRESSURE=cheb PMAXIT=400
  run_one $MAXN "weak_np${MAXN}_meanall.json" env MEANSCOPE=all
  run_one $MAXN "weak_np${MAXN}_amg.json"     env GRAPHAMG=1
  run_one $MAXN "weak_np${MAXN}_hoststage.json" env PECLET_CORE_GPU_AWARE_MPI=0
fi
echo "done -> $RES"
