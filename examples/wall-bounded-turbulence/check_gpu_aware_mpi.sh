#!/bin/bash
# ==========================================================================================
# Discover + validate CUDA-aware (GPU-aware) MPI on Snellius, so the halo can pass device
# pointers straight to MPI (drops the host-staging copies).
#
#   sbatch check_gpu_aware_mpi.sh          # runs as a batch job -> gpuaware-check-<jobid>.out
#   # or interactively:
#   srun -p gpu_h100 --gpus=2 --ntasks=2 --cpus-per-task=16 -t0:30:00 --account=tes24005 --pty bash
#   ./check_gpu_aware_mpi.sh
#
# It loads the same OpenMPI the solver was built against, adds the UCX-CUDA transports, and runs
# the suite's device-pointer MPI check. If it prints "CUDA-aware MPI works", we enable it in the
# run scripts. Paste the whole output (or the .out file) back.
# ==========================================================================================
#SBATCH --job-name=gpuaware-check
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=2         # 2 GPUs on ONE node -> exercises cuda_ipc/cuda_copy
#SBATCH --ntasks=2               # one rank per GPU
#SBATCH --cpus-per-task=16
#SBATCH --time=00:15:00
#SBATCH --output=gpuaware-check-%j.out
#SBATCH --account=tes24005
set -uo pipefail
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
CHECK="$SUITE/core/tools/cuda_aware_mpi_check.cpp"

module purge
module load 2023
module load OpenMPI/4.1.5-GCC-12.3.0
# Snellius' only GPU-aware UCX is built for CUDA 12.1.1, so the WHOLE stack must be 12.1.1
# (Lmod refuses UCX-CUDA against CUDA/12.4.0). CUDA 12.1 still supports Hopper (sm_90).
module load CUDA/12.1.1

echo "############ 1. UCX-CUDA modules available ############"
module -t avail UCX-CUDA 2>&1 | sed 's/^/  /'
echo
echo "############ 2. loading the matching UCX-CUDA ############"
module load UCX-CUDA/1.14.1-GCCcore-12.3.0-CUDA-12.1.1 2>&1 | sed 's/^/  /' \
  || { echo "  !! could not load UCX-CUDA -- check the list above for the exact name"; }
echo "  loaded UCX-related modules:"; module -t list 2>&1 | grep -iE "ucx|openmpi|cuda" | sed 's/^/    /'
echo
echo "############ 3. does UCX now expose CUDA transports? ############"
ucx_info -d 2>/dev/null | grep -iE "Transport: (cuda|gdr)" | sed 's/^/  /' || echo "  (ucx_info not found or no cuda transports)"
echo
echo "############ 4. build the device-pointer MPI check ############"
export OMPI_MCA_pml=ucx           # force the UCX pml (carries cuda_copy/cuda_ipc); the key setting
export UCX_MEMTYPE_CACHE=n        # recommended with CUDA (avoids a known UCX memtype bug)
# export UCX_TLS=self,sm,cuda_copy,cuda_ipc,rc,gdr_copy   # uncomment if auto-selection misses cuda
mpic++ "$CHECK" -I"${CUDA_HOME:-$EBROOTCUDA}/include" -L"${CUDA_HOME:-$EBROOTCUDA}/lib64" -lcudart -o /tmp/cudampicheck \
  && echo "  built /tmp/cudampicheck" || { echo "  BUILD FAILED"; exit 1; }
echo
echo "############ 5. run it on 2 ranks / 2 GPUs (DEVICE pointers) ############"
mpirun -np 2 /tmp/cudampicheck 2>&1 | sed 's/^/  /'
echo
echo "############ verdict ############"
echo "  If you saw 'device recv CORRECT -- CUDA-aware MPI works' above, GPU-aware MPI is functional."
echo "  Then the run scripts can set PECLET_CORE_GPU_AWARE_MPI=1 + these module/env lines."
