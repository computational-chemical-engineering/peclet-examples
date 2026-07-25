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
##SBATCH --account=your_project
set -euo pipefail
module purge; module load 2023 OpenMPI/4.1.5-GCC-12.3.0 CUDA/12.4.0

SUITE="${SUITE:-$HOME/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}" PECLET_BIND_GPU=1

# fixed medium problem (Delta+=2.0, ~77M cells) that fits from 1 GPU up; no stats, just timing.
export GNY=180 GNX=1131 GNZ=377 CFR=15.68 NSTEPS=300 STATSTART=100000000 DIAG=50 DT=0.02
for N in 1 2 4 8; do
  echo "=================  $N GPU(s)  ================="
  srun --mpi=pmix --ntasks=$N --gpus=$N "$VENV/bin/python" channel_dns_mpi.py 2>&1 | grep -E "gpu-bind|it=|FATAL|done"
done
echo "Read the ms/step from each block; plot ms/step vs N to find the efficient node count."
