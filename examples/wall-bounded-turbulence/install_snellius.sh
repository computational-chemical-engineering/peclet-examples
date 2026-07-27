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
#
# Run as a batch job (recommended -- no terminal to babysit; import check runs on the GPU):
#   sbatch install_snellius.sh h100                    # -> peclet-build-<jobid>.out
#   FRESH=1 sbatch install_snellius.sh h100            # clean rebuild -- REQUIRED when switching CUDA
#                                                      #   version/arch (CMake caches the compiler)
# For a100:  sbatch -p gpu_a100 --cpus-per-task=18 install_snellius.sh a100
# ==========================================================================================
#SBATCH --job-name=peclet-build
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=peclet-build-%j.out
#SBATCH --account=tes24005
set -euo pipefail
TARGET="${1:-h100}"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"

# GPU-aware 2024a toolchain (GCC 13.3 + OpenMPI + CUDA 12.6 + UCX-CUDA 1.16 + Python). One shared
# definition so build and run agree; it fails fast if a Snellius module name has drifted.
ENVDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$ENVDIR/snellius_env.sh"

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
  h100) BACKEND=nvidia-cuda; BUILD=flow/build_cuda_mpi; KA=HOPPER90; CA=90 ;;   # CUDA 12.6 from snellius_env
  a100) BACKEND=nvidia-cuda; BUILD=flow/build_cuda_mpi; KA=AMPERE80; CA=80 ;;
  cpu)  BACKEND=host-openmp;  BUILD=flow/build_omp_mpi; KA=; CA= ;;
  *) echo "usage: $0 [h100|a100|cpu]"; exit 1 ;;
esac
# FRESH=1 wipes the cached Kokkos build/install -- REQUIRED when the CUDA version/arch changed, because
# CMake caches CMAKE_CUDA_COMPILER and a plain reconfigure keeps the OLD nvcc.
if [ "${FRESH:-0}" = "1" ]; then
  echo "FRESH: removing extern/{build,install}/$BACKEND"
  rm -rf "extern/build/$BACKEND" "extern/install/$BACKEND"
fi
if [ "$BACKEND" = "nvidia-cuda" ]; then
  KOKKOS_ARCH=$KA CUDA_ARCH=$CA CUDA_COMPILER=$(which nvcc) tools/bootstrap_deps.sh nvidia-cuda
else
  tools/bootstrap_deps.sh host-openmp
fi

# --- 4. build the flow module WITH the distributed (MPI) step ----------------------------------
#   A venv has no Python.h; point CMake at the base install's headers so FindPython's
#   Development.Module component resolves (INCLUDEPY is correct even from inside the venv).
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
rm -rf "$BUILD"   # always reconfigure flow from scratch (picks up the current nvcc / prefix)
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
