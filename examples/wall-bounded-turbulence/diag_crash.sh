#!/bin/bash
# ==========================================================================================
# Diagnose the cudaErrorIllegalAddress at N=2/N=4 in weak scaling (45M cells/GPU blocks).
# Runs the SMALLEST failing case (N=2, 91M, 377x240x503 blocks) TWICE and keeps FULL logs:
#   (A) host-staged halo (PECLET_CORE_GPU_AWARE_MPI=0) -- the CI-validated, known-good path
#   (B) GPU-aware halo   (PECLET_CORE_GPU_AWARE_MPI=1) -- the newer device-pointer path
# Verdict:
#   A works, B crashes  -> the GPU-aware MPI device-pointer path is the bug (use =0 meanwhile)
#   both crash          -> a distributed-solver/halo bug at 45M blocks, independent of transport
#   both work           -> transient/placement; re-run weak_scaling with these settings
# Full logs kept as diagA.log / diagB.log (paste diagA.log if A crashes -- it has the per-rank
# block decomposition, which pinpoints the geometry).
# ==========================================================================================
#SBATCH --job-name=chan-diag
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1                 # 2 ranks on ONE node (matches the failing weak N=2 placement)
#SBATCH --gpus-per-node=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=16
#SBATCH --time=00:20:00
#SBATCH --output=chan-diag-%j.out
#SBATCH --account=tes24005
set -uo pipefail
source "${SLURM_SUBMIT_DIR:-$PWD}/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}" PECLET_BIND_GPU=0

# the failing case: N=2, 91M, 45.5M/GPU (same block as weak N=2)
export GNX=754 GNY=240 GNZ=503 CFR=15.68 NSTEPS=60 STATSTART=100000000 DIAG=10 DT=0.02 WARMUP=20

run() {  # label  gpu_aware
  echo "############################  ($1)  PECLET_CORE_GPU_AWARE_MPI=$2  ############################"
  PECLET_CORE_GPU_AWARE_MPI=$2 srun --mpi=pmix --ntasks=2 --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" channel_dns_mpi.py > "diag$1.log" 2>&1 && st=OK || st=FAILED
  echo "  --> $st"
  grep -E "cfg\]|rank [0-9]:|gpu-bind|OK: every|WARNING|it=|timing|Illegal|illegal|error\(" "diag$1.log" \
    | grep -viE "save_stacktrace|host_abort|SharedAllocation" | head -25 | sed 's/^/    /'
  echo
}
run A 0     # host-staged (known good)
run B 1     # GPU-aware (device pointers)
echo "Verdict: A-ok+B-fail => GPU-aware path bug; both-fail => solver/halo bug at 45M blocks."
