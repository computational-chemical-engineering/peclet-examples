#!/bin/bash
# ==========================================================================================
# Turbulent channel-flow DNS (Re_tau=180) on Snellius GPU nodes — multi-GPU, one MPI rank per GPU.
#
#   Full MKM box 4piH x 2H x (4/3)piH, isotropic grid.  Delta+ = 360/GNY.
#   Recommended production point:  Delta+=1.5  ->  GNY=240, GNX=1508, GNZ=503  (~182 M cells).
#     - fits 1 H100 node (4 x 94 GB) with headroom, or 2 A100 nodes (8 x 40 GB).
#   Hero point:  Delta+=1.0  ->  GNY=360, GNX=2262, GNZ=754  (~614 M cells)  -> 3 H100 nodes.
#
#   Edit the SBATCH block for your allocation, then:  sbatch snellius_gpu.slurm
# ==========================================================================================
#SBATCH --job-name=chan-dns
#SBATCH --partition=gpu_h100          # H100 (4x94GB). For A100 use --partition=gpu and bump --nodes.
#SBATCH --nodes=1                     # 1 H100 node = 4 GPUs, fits the 182M (Delta+=1.5) case.
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4           # one MPI rank per GPU
#SBATCH --cpus-per-task=16            # 64 cores / 4 ranks (H100 node); use 18 on A100 (72/4)
#SBATCH --time=08:00:00
#SBATCH --output=chan-dns-%j.out
##SBATCH --account=your_project       # <-- set your accounting project (run: accinfo)
set -euo pipefail

# --- environment: match the modules used to BUILD the suite (see install_snellius.sh) ----------
module purge
module load 2023
module load foss/2023a               # GCC + OpenMPI 4.1.x  (CUDA-aware if built --with-cuda)
module load CUDA/12.4.0

SUITE="${SUITE:-$HOME/peclet/suite}"                     # where you cloned + built the suite
BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"             # the PECLET_FLOW_MPI=ON CUDA build
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"

# --- problem size (Delta+ = 360/GNY) -----------------------------------------------------------
export GNY="${GNY:-240}"
export GNX="${GNX:-$(python3 -c "import math;print(round(2*math.pi*$GNY))")}"   # 4piH box -> 2pi*GNY
export GNZ="${GNZ:-$(python3 -c "import math;print(round(2*math.pi/3*$GNY))")}" # (4/3)piH  -> (2pi/3)*GNY
export CFR="${CFR:-15.68}"            # hold bulk U+ (MKM value) -> emergent u_tau/Re_tau
export NSTEPS="${NSTEPS:-50000}"     # ~5-10 eddy-turnovers for converged statistics
export STATSTART="${STATSTART:-20000}" ; export STATEVERY="${STATEVERY:-25}"
export DT="${DT:-0.02}" ; export DIAG="${DIAG:-500}" ; export ADV=0
export OUT="${OUT:-chan_${GNY}_${SLURM_JOB_ID}}"

export PECLET_BIND_GPU=1             # driver binds rank -> node-local GPU (before import)
# export PECLET_CORE_GPU_AWARE_MPI=1 # opt-in: device-pointer halo (needs CUDA-aware OpenMPI+UCX)

echo "grid ${GNX}x${GNY}x${GNZ}  ranks=$SLURM_NTASKS  nodes=$SLURM_NNODES"
srun --mpi=pmix "$VENV/bin/python" channel_dns_mpi.py
echo "done -> ${OUT}_stats.npz  (post-process locally: python analyze_channel.py ${OUT}_stats.npz out.png)"
