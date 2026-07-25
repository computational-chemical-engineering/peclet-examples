#!/bin/bash
# ==========================================================================================
# Build the peclet `flow` solver (Kokkos + MPI) from source on Snellius.
#   GPU (default):  ./install_snellius.sh h100      # or a100
#   CPU:            ./install_snellius.sh cpu
# Run on a login node, or better an interactive build node:
#   srun -p gpu_h100 --gpus=1 -n1 -c16 -t2:00:00 --pty bash   # then ./install_snellius.sh h100
#
# NOTE (verified 2026-07-25): module versions on Snellius drift. The lines below are the suite's
# reference stack; if `module avail 2023` shows a version is gone, load the nearest one -- the only
# hard requirement is that this OpenMPI is the SAME one mpi4py links against (pip builds mpi4py
# against whatever `mpicc` is on PATH here).
# ==========================================================================================
set -euo pipefail
TARGET="${1:-h100}"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"

module purge
module load 2023
module load OpenMPI/4.1.5-GCC-12.3.0         # GCC 12.3 + OpenMPI 4.1.5
module load Python/3.11.3-GCCcore-12.3.0     # >=3.10 required (system python3 is 3.9); `module avail 2023 Python`

# --- 1. clone (or update) the suite + submodules ----------------------------------------------
#   flow now consumes core/scheme headers, so core and flow MUST be at matching (umbrella-pinned)
#   commits -- always update submodules together before building.
#   The umbrella's .gitmodules use SSH URLs (git@github.com:); compute nodes have no GitHub SSH key,
#   so rewrite SSH->HTTPS for the (public) repos. Harmless + idempotent.
git config --global url."https://github.com/".insteadOf "git@github.com:"
if [ ! -d "$SUITE/.git" ]; then
  git clone --recurse-submodules https://github.com/computational-chemical-engineering/peclet.git "$SUITE"
fi
cd "$SUITE"
git pull --ff-only || true
git submodule update --init --recursive       # <-- keeps core + flow in lockstep (now over HTTPS)

# --- 2. python venv (nanobind via the active interpreter; mpi4py built against the loaded OpenMPI)
#   --clear rebuilds the venv with the CURRENT python3 (3.11) even if a stale 3.9 venv exists.
python3 -c 'import sys; assert sys.version_info[:2]>=(3,10), f"need Python>=3.10, got {sys.version}"'
python3 -m venv --clear flow/.venv
source flow/.venv/bin/activate
pip install -U pip nanobind numpy mpi4py matplotlib

# --- 3. (re)bootstrap the pinned Kokkos for the right backend/arch ------------------------------
#   Re-run even if you bootstrapped before: the nvidia-cuda bootstrap gained Kokkos_ENABLE_CUDA_CONSTEXPR
#   (2026-07-23) -- an old prefix can silently miscompile device code. It's cheap; just do it.
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
#   A venv has no Python.h; point CMake at the base install's headers so FindPython's
#   Development.Module component resolves (INCLUDEPY is correct even from inside the venv).
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
cmake -S flow -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DPECLET_FLOW_MPI=ON \
  -DPython_EXECUTABLE="$PWD/flow/.venv/bin/python" \
  -DPython_INCLUDE_DIR="$PYINC" \
  -DCMAKE_PREFIX_PATH="$PWD/extern/install/$BACKEND" \
  -DMPIEXEC_EXECUTABLE="$(which mpirun)"
cmake --build "$BUILD" -j"$(nproc)"

echo
echo "Built $BUILD/peclet/flow/_flow*.so"
# import check needs a GPU for the CUDA backend; harmless to skip on a login node (the .so is built).
PYTHONPATH="$PWD/$BUILD" python -c "from peclet import flow; print('backend:', flow.execution_space, '| has_mpi:', flow.has_mpi)" \
  || echo "(import check skipped — run on a GPU node; the module is built. has_mpi must be True there.)"
echo "-> The SLURM scripts default to exactly this build:  SUITE=$SUITE  BUILD=$PWD/$BUILD"
