#!/bin/bash
# ==========================================================================================
# WEAK scaling — the meaningful test for "can I run a bigger DNS on more GPUs in the same time?"
# Keeps cells-PER-GPU fixed (~production 45M/GPU) and grows the global problem with GPU count.
# Ideal weak scaling = constant ms/step across N. (Strong scaling of a fixed small box collapses
# because the pressure Poisson solve is global-reduction bound at low cells/GPU -- see the page.)
#
#   sbatch --nodes=2 weak_scaling.sh          # sweeps 1,2,4,8 GPUs at ~45M cells each
# ==========================================================================================
#SBATCH --job-name=chan-weak
#SBATCH --partition=gpu_h100
#SBATCH --nodes=2
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=01:30:00
#SBATCH --output=chan-weak-%j.out
#SBATCH --account=tes24005
set -uo pipefail
source "${SLURM_SUBMIT_DIR:-$PWD}/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI=1

# Per-GPU block: GNY,GNZ fixed (production Delta+=1.5 cross-section, y NEVER split); GNX grows with N.
# base GNX=377 -> 377x240x503 = 45.5M cells/GPU. N=4 lands exactly on the 182M production grid.
export GNY=240 GNZ=503 CFR=15.68 NSTEPS=250 STATSTART=100000000 DIAG=50 DT=0.02 WARMUP=50
BASE_GNX=377
echo "weak scaling: ~$(python3 -c "print(f'{$BASE_GNX*240*503/1e6:.0f}')")M cells/GPU fixed; GNX grows with N"
for N in 1 2 4 8; do
  export GNX=$(( BASE_GNX * N ))
  echo "=================  $N GPU(s) : ${GNX}x${GNY}x${GNZ} = $(python3 -c "print(f'{$GNX*$GNY*$GNZ/1e6:.0f}')")M cells  ================="
  srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
       "$VENV/bin/python" channel_dns_mpi.py > "weak_N${N}.log" 2>&1 || true
  if grep -q "timing" "weak_N${N}.log"; then
    grep -E "gpu-bind\]|WARNING|OK: every|timing" "weak_N${N}.log"
  else
    echo "  [FAILED N=$N] real error:"
    grep -iE "error|traceback|no module|cuda|cupy|out of memory|fatal|FAILED" "weak_N${N}.log" \
      | grep -viE "Kokkos4Impl|host_abort|SharedAllocation|save_stacktrace|Backtrace|^\s*\[0x|\[gcn|libpython|libc\.so|_start|__libc" \
      | head -10 | sed 's/^/    /'
  fi
done
echo
echo "Ideal weak scaling: steady ms/step stays ~CONSTANT as N grows. Rising ms/step = the pressure-solve"
echo "communication tax (global reductions), worst across nodes (N=4->8 crosses from 1 to 2 nodes)."
