#!/bin/bash
# ==========================================================================================
# Pinpoint the cudaErrorIllegalAddress at large per-rank blocks with compute-sanitizer.
# Runs the smallest reliably-failing case (N=2, 91M = 45.5M/GPU blocks) under memcheck, which
# reports the EXACT kernel + source line of the out-of-bounds device access. Slow (sanitizer adds
# large overhead) but only needs to reach the first crashing step -- keep NSTEPS tiny.
#
#   sbatch diag_sanitizer.sh   ->  chan-san-<jobid>.out  (paste the "Invalid __global__ read/write"
#   block + the backtrace it prints; that names the kernel and file:line to fix in flow/core).
# ==========================================================================================
#SBATCH --job-name=chan-san
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=2
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=16
#SBATCH --time=00:40:00
#SBATCH --output=chan-san-%j.out
#SBATCH --account=tes24005
set -uo pipefail
source "${SLURM_SUBMIT_DIR:-$PWD}/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI=0   # host-staged: isolate the compute kernel, not MPI
# sanitizer needs headroom + blocking launches so the fault is attributed to the right kernel:
export CUDA_LAUNCH_BLOCKING=1

export GNX=754 GNY=240 GNZ=503 CFR=15.68 NSTEPS=2 DT=0.02 DIAG=1 STATSTART=100000000 WARMUP=1

command -v compute-sanitizer >/dev/null && SAN=compute-sanitizer || SAN=cuda-memcheck
echo "using $SAN  ($(command -v $SAN))"
# one sanitizer per rank; --launch-timeout 0 since kernels are slow under the tool.
srun --mpi=pmix --ntasks=2 --gpus-per-task=1 --gpu-bind=per_task:1 \
  $SAN --tool memcheck --launch-timeout 0 --print-limit 1 \
  "$VENV/bin/python" channel_dns_mpi.py 2>&1 | \
  grep -A25 -iE "Invalid __global__|Invalid __shared__|out-of-bounds|Program hit|=== ERROR|ERROR SUMMARY|by .*flow|_flow\.cpython|\.hpp:|\.cpp:" | head -120
echo "(if nothing above: paste the full chan-san-<jobid>.out — the sanitizer block may be formatted differently)"
