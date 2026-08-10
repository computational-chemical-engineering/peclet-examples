#!/bin/bash
# ==========================================================================================
# Channel-DNS weak scaling on Snellius gpu_h100 — 46.4M cells/GPU fixed.
#
# The per-GPU block is IDENTICAL at every point: GNY=240, GNZ=503 (the production Delta+=1.5
# cross-section; y is the wall-normal direction and must NEVER be split) and GNX = 384*N, so the
# ORB carves x into N blocks of exactly 384x240x503 = 46.4M cells. 384 is chosen over the
# production 377 purely for divisibility: every rank then owns a byte-identical block at every N,
# which is what a weak-scaling curve is supposed to compare. N=4 (1536x240x503 = 185M) is the
# production DNS box to within 2 %.
#
# Argument = the GPU count to measure (queue-parallel safe: each job touches only its own point),
# or 'levers' for the ablation at the allocated max. Argument, not env var — SURF sbatch drops
# leading env vars.
#   sbatch --nodes=1 chan_weak_gpu.sh 1
#   sbatch --nodes=1 chan_weak_gpu.sh 2
#   sbatch --nodes=1 chan_weak_gpu.sh 4
#   sbatch --nodes=2 chan_weak_gpu.sh 8
#   sbatch --nodes=4 chan_weak_gpu.sh 16
#   sbatch --nodes=8 chan_weak_gpu.sh 32
#   sbatch --nodes=2 chan_weak_gpu.sh levers      # CPG / mean-scope / MG depth / halo, at N=8
#   sbatch --nodes=2 chan_weak_gpu.sh strong      # OPTIONAL: fixed 46M box on 1,2,4,8 GPUs
#
# Second argument = result TAG appended to every JSON (`chan_weak_gpu.sh 8 r2`). run_one SKIPS a
# JSON that already exists, so a re-measurement (solver change, repeat draw) NEEDS a new tag —
# otherwise the stale file is silently reported as the new number.
# ==========================================================================================
#SBATCH --job-name=chan-weak
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=00:40:00
#SBATCH --output=chan-weak-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
EXAMPLE="$EXDIR/../../../examples/wall-bounded-turbulence"
source "$EXAMPLE/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI="${GPU_AWARE:-1}"
RES="$EXDIR/../results/snellius-h100"; mkdir -p "$RES"

# Production channel physics: Re_tau=180, isotropic unit grid, SOU advection, CFR forcing (holds the
# bulk velocity — its own global Allreduce per step, outside the pressure solve; the `cpg` lever
# quantifies it). 100 warmup + 40 measured steps; DIAG=100 keeps the live diagnostic (and its
# gather) OUT of the measured window while still printing one sanity line per run.
export GNY=240 GNZ=503 DT=0.02 ADV=0 CFR=15.68 RE_TAU=180 NOISE=1.0 SEED=1234
export WARMUP=100 NSTEPS=140 DIAG=100 STATSTART=1000000000 CKPT=0 HB=20
BASE_GNX=384
MAXN=$(( SLURM_NNODES * 4 ))

FIXED_GNX=0    # strong-scaling mode sets this: same box on every rank count

run_one () {  # N out extra-env...
  local N=$1 out=$2; shift 2
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  local gnx=$(( FIXED_GNX > 0 ? FIXED_GNX : BASE_GNX * N ))
  echo "======= N=$N : ${gnx}x${GNY}x${GNZ} = $(( gnx * GNY * GNZ / 1000000 ))M cells  ($out) ======="
  env GNX=$gnx LABEL="snellius-h100" BENCH_OUT="$RES/$out" \
      OUT="${TMPDIR:-/tmp}/chan_${out%.json}" "$@" \
    srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXAMPLE/channel_dns_mpi.py" > "$RES/${out%.json}.log" 2>&1
  # NEVER trust the exit status: the JSON is the only success criterion.
  if [ -f "$RES/$out" ]; then
    grep -E "^\[(timing|phases)" "$RES/${out%.json}.log"
  else
    echo "  [FAILED N=$N] no JSON (full log: $RES/${out%.json}.log):"
    grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
    grep -m3 -iE "FATAL|Error:|ModuleNotFound|ImportError|out of memory|assert" \
      "$RES/${out%.json}.log" | sed 's/^/    /'
  fi
}

ARG="${1:-}"; TAG="${2:+_${2}}"
# OPTIONAL strong scaling: the ONE-GPU box (46.4M) split over more and more GPUs, down to 5.8M
# cells/GPU at N=8 — where the pressure solve's global reductions dominate the shrinking local work.
# 384/N stays a multiple of the MG coarsen-alignment (16) up to N=8, so blocks stay even.
if [ "$ARG" = strong ]; then
  FIXED_GNX=$BASE_GNX
  for N in 1 2 4 8; do
    [ "$N" -le "$MAXN" ] && run_one $N "chan_strong_np${N}${TAG}.json"
  done
  echo "done -> $RES"; exit 0
fi
if [ -n "$ARG" ] && [ "$ARG" != levers ]; then
  [ "$ARG" -le "$MAXN" ] || { echo "FATAL: N=$ARG needs $(( (ARG+3)/4 )) nodes, allocated $SLURM_NNODES" >&2; exit 1; }
  run_one "$ARG" "chan_np${ARG}${TAG}.json"
else
  for N in 1 2 4 8 16 32; do
    [ "$N" -le "$MAXN" ] && run_one $N "chan_np${N}${TAG}.json"
  done
fi

# Ablation at the largest allocated N — the channel-specific suspects, one variable at a time:
#   cpg       CFR forcing off (constant pressure gradient) = the forcing Allreduce removed
#   meanall   legacy pressure mean-removal scope (~3x more global reductions per Krylov iteration)
#   mg4/mg6   multigrid depth: GNZ=503 is odd and never coarsens, so the coarse levels are
#             semi-coarsened slabs — does more/less depth help or hurt at scale?
#   hoststage GPU-aware MPI off (halos staged through host memory)
if [ "$ARG" = levers ] || [ "${LEVERS:-0}" = 1 ]; then
  run_one $MAXN "chan_np${MAXN}_cpg${TAG}.json"       env CFR=0
  run_one $MAXN "chan_np${MAXN}_meanall${TAG}.json"   env MEANSCOPE=all
  run_one $MAXN "chan_np${MAXN}_mg4${TAG}.json"       env MGLEVELS=4
  run_one $MAXN "chan_np${MAXN}_mg6${TAG}.json"       env MGLEVELS=6
  run_one $MAXN "chan_np${MAXN}_hoststage${TAG}.json" env PECLET_CORE_GPU_AWARE_MPI=0
fi
echo "done -> $RES"
