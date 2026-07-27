#!/bin/bash
# ==========================================================================================
# Turbulent channel-flow DNS (Re_tau=180) on Snellius GPU nodes — multi-GPU, one MPI rank per GPU.
#
#   Full MKM box 4piH x 2H x (4/3)piH, isotropic grid.  Delta+ = 360/GNY.
#   Recommended production point:  Delta+=1.5  ->  GNY=240, GNX=1508, GNZ=503  (~182 M cells).
#     - fits 1 H100 node (4 x 94 GB) with headroom, or 2 A100 nodes (8 x 40 GB).
#   Hero point:  Delta+=1.0  ->  GNY=360, GNX=2262, GNZ=754  (~614 M cells)  -> 3 H100 nodes.
#
#   >>> BEFORE YOU SUBMIT (verified 2026-07-25 against SURF docs; confirm on the machine): <<<
#     - Partitions (run `sinfo -s`):  gpu_h100 (4x H100 94GB, 64 cores)  |  gpu_a100 (4x A100 40GB, 72 cores).
#       (The bare `gpu` partition no longer exists.)  Set --cpus-per-task = cores_per_node / 4.
#     - Modules (run `module avail 2023`): the versions below match the suite's reference build; if a
#       version is gone, pick the nearest and rebuild with install_snellius.sh so mpi4py/OpenMPI agree.
#     - Set your accounting project below (run `accinfo` to see yours).  Max walltime is 120 h.
#     - On-cluster multi-node has NOT been validated by the suite — run scaling_test.sh first (see the page).
#
#   Submit:  sbatch snellius_gpu.slurm            # 1 H100 node, Delta+=1.5 (182M)
#            GNY=360 sbatch --nodes=3 snellius_gpu.slurm   # hero, Delta+=1.0 (614M)
# ==========================================================================================
#SBATCH --job-name=chan-dns
#SBATCH --partition=gpu_h100          # H100 (4x94GB, 64c). A100: --partition=gpu_a100 (4x40GB, 72c).
#SBATCH --nodes=1                     # 1 H100 node = 4 GPUs, fits the 182M (Delta+=1.5) case.
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4           # one MPI rank per GPU
#SBATCH --cpus-per-task=16            # 64 cores / 4 (gpu_h100).  Use 18 on gpu_a100 (72/4).
#SBATCH --time=08:00:00               # max 120:00:00
#SBATCH --output=chan-dns-%j.out
#SBATCH --account=tes24005
set -euo pipefail

# --- environment: MUST match the toolchain used to BUILD (see install_snellius.sh) -------------
source "${SLURM_SUBMIT_DIR:-$PWD}/snellius_env.sh"   # 2024a GPU-aware stack; sets OMPI_MCA_pml=ucx etc.

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"            # the PECLET_FLOW_MPI=ON CUDA build
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"

# --- problem size (Delta+ = 360/GNY) -----------------------------------------------------------
export GNY="${GNY:-240}"
export GNX="${GNX:-$(python3 -c "import math;print(round(2*math.pi*$GNY))")}"   # 4piH -> 2pi*GNY
export GNZ="${GNZ:-$(python3 -c "import math;print(round(2*math.pi/3*$GNY))")}" # (4/3)piH -> (2pi/3)*GNY
export CFR="${CFR:-15.68}"            # hold bulk U+ (MKM value) -> emergent u_tau/Re_tau
export NSTEPS="${NSTEPS:-50000}"     # ~5-10 eddy-turnovers for converged statistics
export STATSTART="${STATSTART:-20000}" ; export STATEVERY="${STATEVERY:-25}"
export DT="${DT:-0.02}" ; export DIAG="${DIAG:-500}" ; export ADV=0
export OUT="${OUT:-chan_${GNY}_${SLURM_JOB_ID}}"

# rank->GPU binding is done inside the driver (node-local rank picks its GPU BEFORE import); the
# driver prints CUDA_VISIBLE_DEVICES per rank at startup -- CHECK they are distinct within a node.
export PECLET_BIND_GPU=1
# GPU-aware MPI: device pointers straight into the halo (2024a stack has CUDA-aware UCX-CUDA, validated
# by check_gpu_aware_mpi.sh). snellius_env.sh already set OMPI_MCA_pml=ucx + UCX_MEMTYPE_CACHE=n.
# Set =0 to fall back to host-staging (always correct) if you ever change the MPI stack.
export PECLET_CORE_GPU_AWARE_MPI=1

echo "grid ${GNX}x${GNY}x${GNZ}  ranks=$SLURM_NTASKS  nodes=$SLURM_NNODES"
srun --mpi=pmix "$VENV/bin/python" channel_dns_mpi.py
echo "done -> ${OUT}_stats.npz  (post-process: python analyze_channel.py ${OUT}_stats.npz out.png)"
