#!/bin/bash
# ==========================================================================================
# Strong-scaling test — run BEFORE committing a big allocation. On-cluster multi-node has not
# been validated by the suite, so measure the real throughput and parallel efficiency here.
#
#   Fixed problem, short run, sweep 1 -> 2 -> 4 -> 8 GPUs. Watch ms/step: if it halves each time
#   you double the GPUs you have near-ideal strong scaling; where it flattens is your efficient
#   node count. Also confirms rank->GPU binding (distinct CUDA_VISIBLE_DEVICES per rank) and that
#   the ORB kept the wall-normal (y) direction whole (the driver aborts otherwise).
#
#   sbatch --nodes=2 scaling_test.sh        # gives up to 8 H100 GPUs to sweep
# ==========================================================================================
#SBATCH --job-name=chan-scale
#SBATCH --partition=gpu_h100
#SBATCH --nodes=2
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=01:00:00
#SBATCH --output=chan-scale-%j.out
#SBATCH --account=tes24005
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-$PWD}/snellius_env.sh"   # 2024a GPU-aware stack

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0              # SLURM binds 1 GPU/task (srun flags below); driver must NOT remap
export PECLET_CORE_GPU_AWARE_MPI=1   # device-pointer halo (validated); =0 host-stages

# Fixed problem that MUST fit on ONE GPU (strong scaling). ~27.6M cells (~40 GB) fits 1 H100 (94 GB)
# with margin. On gpu_a100 (40 GB) use GNY=112 (~18.5M) instead — a full 27.6M won't fit one A100.
export GNY="${GNY:-128}"
export GNX="${GNX:-$(python3 -c "import math;print(round(2*math.pi*$GNY))")}"
export GNZ="${GNZ:-$(python3 -c "import math;print(round(2*math.pi/3*$GNY))")}"
export CFR=15.68 NSTEPS=300 STATSTART=100000000 DIAG=50 DT=0.02   # STATSTART huge -> pure timing, no stats
echo "scaling problem: ${GNX}x${GNY}x${GNZ} = $(python3 -c "print(f'{$GNX*$GNY*$GNZ/1e6:.0f}')")M cells (fixed; strong scaling)"
for N in 1 2 4 8; do
  echo "=================  $N GPU(s)  ================="
  # --gpus-per-task=1 + --gpu-bind=per_task:1 -> SLURM cgroup-isolates each task to its OWN GPU
  # (the reliable one-rank-one-GPU mechanism on Snellius; manual CUDA_VISIBLE_DEVICES juggling
  # oversubscribed GPUs and wrecked scaling). Full output -> per-N log; keep going on failure.
  srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
       "$VENV/bin/python" channel_dns_mpi.py > "scale_N${N}.log" 2>&1 || true
  if grep -q "it=" "scale_N${N}.log"; then
    grep -E "gpu-bind\]|WARNING|OK: every|it=|timing|done" "scale_N${N}.log"
  else
    # no timing -> real error. Filter out the benign Kokkos-finalize teardown backtrace to show the CAUSE.
    echo "  [FAILED N=$N] real error (teardown noise filtered):"
    grep -iE "error|traceback|no module|module.*not|exception|assert|cuda|cupy|out of memory|cannot|fatal|FAILED" \
         "scale_N${N}.log" \
      | grep -viE "Kokkos4Impl|host_abort|SharedAllocation|save_stacktrace|Backtrace|^\s*\[0x|\[gcn|libpython|libc\.so|_start|__libc|task-epilog" \
      | head -12 | sed 's/^/    /'
  fi
done
echo
echo "From each block: the '[NN.N it/s]' at the end of the it= lines is the throughput."
echo "ms/step = 1000 / it_per_s.  Ideal strong scaling: it/s roughly doubles 1->2->4->8 GPUs."
