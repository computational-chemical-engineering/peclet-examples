#!/bin/bash
# ==========================================================================================
# Turbulent channel-flow DNS (Re_tau=180) on Snellius CPU (Genoa) nodes — MPI + OpenMP.
#
#   Same physics as the GPU script; use when no GPU allocation is available. CPU is memory-cheap
#   (218 GB for the 182M case fits in one 384 GB Genoa node) but compute-bound: you need many
#   nodes for a reasonable wall-clock, and the global pressure solve limits scaling past ~a few
#   thousand cores. Run a scaling test (1/2/4/8 nodes, few hundred steps) before a big job.
#
#   Rule of thumb (Delta+=1.5, 182M cells): ~16 Genoa nodes ~ 13 h ; ~32 nodes ~ 6 h.
#   Keep the ORB from splitting the wall-normal y: <= ~32 ranks-in-y is safe (the driver aborts
#   if it would). Use FEW fat MPI ranks x many OpenMP threads (e.g. 2 ranks/node x 96 threads)
#   so the rank grid stays coarse and y is never split.
# ==========================================================================================
#SBATCH --job-name=chan-dns-cpu
#SBATCH --partition=genoa            # 192 cores, 384 GB/node
#SBATCH --nodes=16
#SBATCH --ntasks-per-node=2          # 2 MPI ranks/node ...
#SBATCH --cpus-per-task=96           # ... x 96 OpenMP threads = 192 cores/node
#SBATCH --time=15:00:00
#SBATCH --output=chan-dns-cpu-%j.out
##SBATCH --account=your_project
set -euo pipefail

module purge
module load 2023
module load foss/2023a               # GCC + OpenMPI

SUITE="${SUITE:-$HOME/peclet/suite}"
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
