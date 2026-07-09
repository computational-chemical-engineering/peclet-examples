#!/bin/bash
# ==========================================================================================
# Build the peclet `flow` solver (Kokkos + MPI) from source on Snellius.
#   GPU (default):  ./install_snellius.sh h100      # or a100
#   CPU:            ./install_snellius.sh cpu
# Run this on a LOGIN node (compiling), or better an interactive build node:
#   srun -p gpu_h100 --gpus=1 -n1 -c16 -t2:00:00 --pty bash   # then ./install_snellius.sh h100
# ==========================================================================================
set -euo pipefail
TARGET="${1:-h100}"
SUITE="${SUITE:-$HOME/peclet/suite}"

module purge
module load 2023
module load foss/2023a                       # GCC 12.3 + OpenMPI 4.1.x

# --- 1. clone the suite (submodules: flow, dem, core, voro, morton) ----------------------------
if [ ! -d "$SUITE/.git" ]; then
  git clone --recurse-submodules https://github.com/computational-chemical-engineering/peclet.git "$SUITE"
fi
cd "$SUITE"

# --- 2. python venv (nanobind found via the active interpreter; mpi4py for the driver) ---------
python3 -m venv flow/.venv
source flow/.venv/bin/activate
pip install -U pip nanobind numpy mpi4py matplotlib

# --- 3. bootstrap the pinned Kokkos for the right backend/arch ---------------------------------
case "$TARGET" in
  h100) module load CUDA/12.4.0; BACKEND=nvidia-cuda; BUILD=flow/build_cuda_mpi
        KOKKOS_ARCH=HOPPER90 CUDA_ARCH=90 CUDA_COMPILER=$(which nvcc) tools/bootstrap_deps.sh nvidia-cuda ;;
  a100) module load CUDA/12.4.0; BACKEND=nvidia-cuda; BUILD=flow/build_cuda_mpi
        KOKKOS_ARCH=AMPERE80 CUDA_ARCH=80 CUDA_COMPILER=$(which nvcc) tools/bootstrap_deps.sh nvidia-cuda ;;
  cpu)  BACKEND=host-openmp; BUILD=flow/build_omp_mpi
        tools/bootstrap_deps.sh host-openmp ;;
  *) echo "usage: $0 [h100|a100|cpu]"; exit 1 ;;
esac

# --- 4. build the flow module WITH the distributed (MPI) step ----------------------------------
cmake -S flow -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DPECLET_FLOW_MPI=ON \
  -DPython_EXECUTABLE="$PWD/flow/.venv/bin/python" \
  -DCMAKE_PREFIX_PATH="$PWD/extern/install/$BACKEND" \
  -DMPIEXEC_EXECUTABLE="$(which mpirun)"
cmake --build "$BUILD" -j"$(nproc)"

echo
echo "Built $BUILD/peclet/flow/_flow*.so"
PYTHONPATH="$PWD/$BUILD" python -c "from peclet import flow; print('backend:', flow.execution_space, '| has_mpi:', flow.has_mpi)"
echo "Set in the SLURM script:  SUITE=$SUITE  BUILD=$PWD/$BUILD"
