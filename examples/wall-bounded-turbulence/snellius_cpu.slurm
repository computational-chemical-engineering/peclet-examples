#!/bin/bash
# ==========================================================================================
# Turbulent channel-flow DNS (Re_tau=180) on Snellius CPU (Genoa) nodes — MPI + OpenMP.
#
#   NOTE: needs a CPU allocation (genoa/rome product). On this account that is the NWO-2024.005
#   project (~4M SBU on genoa); the GPU project (2307092_26) has no CPU product. `--account` below
#   is the login account (tes24005) — SURF routes to the budget whose product matches the partition
#   (genoa -> NWO-2024.005). If a job is rejected for accounting, set --account to the project code.
#
#   Same physics as the GPU script; the GPU path is recommended (far cheaper wall-clock). CPU is memory-cheap
#   (218 GB for the 182M case fits in one 336 GiB-usable Genoa node) but compute-bound: you need
#   many nodes for a reasonable wall-clock, and the global pressure solve limits scaling past ~a
#   few thousand cores. Run a scaling test (1/2/4/8 nodes, few hundred steps) before a big job.
#
#   Rule of thumb (Delta+=1.5, 182M cells): ~16 Genoa nodes ~ 13 h ; ~32 nodes ~ 6 h.
#   Keep the ORB from splitting the wall-normal y: <= ~32 ranks-in-y is safe (the driver aborts
#   if it would). Use FEW fat MPI ranks x many OpenMP threads (e.g. 2 ranks/node x 96 threads)
#   so the rank grid stays coarse and y is never split.
# ==========================================================================================
#SBATCH --job-name=chan-dns-cpu
#SBATCH --partition=genoa            # 192 cores, 336 GiB usable/node
#SBATCH --nodes=16
#SBATCH --ntasks-per-node=2          # 2 MPI ranks/node ...
#SBATCH --cpus-per-task=96           # ... x 96 OpenMP threads = 192 cores/node
#SBATCH --time=15:00:00
#SBATCH --output=chan-dns-cpu-%j.out
#SBATCH --account=tes24005
set -euo pipefail

module purge
module load 2023
module load OpenMPI/4.1.5-GCC-12.3.0   # suite reference stack; `module avail 2023` to confirm

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/flow/build_omp_mpi}"             # PECLET_FLOW_MPI=ON, host-openmp prefix
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export OMP_PROC_BIND=spread OMP_PLACES=threads

export GNY="${GNY:-240}"
export GNX="${GNX:-$(python3 -c "import math;print(round(2*math.pi*$GNY))")}"
export GNZ="${GNZ:-$(python3 -c "import math;print(round(2*math.pi/3*$GNY))")}"
export CFR="${CFR:-15.68}" NSTEPS="${NSTEPS:-50000}" STATSTART="${STATSTART:-20000}"
export STATEVERY=25 DT=0.02 DIAG=500 ADV=0 OUT="${OUT:-chan_${GNY}_${SLURM_JOB_ID}}"

echo "grid ${GNX}x${GNY}x${GNZ}  ranks=$SLURM_NTASKS x ${OMP_NUM_THREADS} threads"
srun --cpus-per-task=$SLURM_CPUS_PER_TASK "$VENV/bin/python" channel_dns_mpi.py
