#!/bin/bash
# ==========================================================================================
# Build the PINNED benchmark worktree ($SUITE/fb/flow + $SUITE/fb/core) for foxberry-scaling.
#
# Why a worktree and not $SUITE/flow: the main checkout carries an in-progress campaign
# (uncommitted edits to src/{cut_cell_ibm,flow_bindings,flow_ibm}.hpp) and sits at an older
# commit. The benchmark needs a clean, known flow -- and its build must NOT disturb that work.
# fb/flow and fb/core sit side by side so flow's `../core/include` resolution finds the matching
# core (PecletDeps.cmake: peclet_sibling_include).
#
# Create the worktrees once (login node):
#   S=/projects/0/prjs1022/peclet/suite
#   git -C $S/flow fetch origin && git -C $S/flow worktree add $S/fb/flow <flow-sha>
#   git -C $S/core fetch origin && git -C $S/core worktree add $S/fb/core <core-sha>
#
# Then:  sbatch build_fb.sh cpu      # -> fb/flow/build_omp_mpi   (genoa runs)
#        sbatch build_fb.sh h100     # -> fb/flow/build_cuda_mpi  (gpu_h100 runs)
#
# Reuses the already-bootstrapped $SUITE/extern/install/<backend> prefix and the shared venv.
# ==========================================================================================
#SBATCH --job-name=fb-build
#SBATCH --partition=genoa
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --time=01:00:00
#SBATCH --output=fb-build-%j.out
#SBATCH --account=tes24005
set -euo pipefail
TARGET="${1:-cpu}"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"

case "$TARGET" in
  cpu)  BACKEND=host-openmp;  BUILD="$SUITE/fb/flow/build_omp_mpi"
        module purge; module load 2024 gompi/2024a
        module load Python/3.12.3-GCCcore-13.3.0 2>/dev/null || true ;;
  h100) BACKEND=nvidia-cuda;  BUILD="$SUITE/fb/flow/build_cuda_mpi"
        source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh" ;;
  *) echo "usage: sbatch build_fb.sh [cpu|h100]"; exit 1 ;;
esac

[ -d "$SUITE/fb/flow" ] || { echo "FATAL: $SUITE/fb/flow missing (create the worktrees first)"; exit 1; }
[ -d "$SUITE/fb/core" ] || { echo "FATAL: $SUITE/fb/core missing (flow needs ../core/include)"; exit 1; }

VENV="$SUITE/flow/.venv"
source "$VENV/bin/activate"
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')

echo "[fb-build] target=$TARGET backend=$BACKEND"
echo "[fb-build] flow $(git -C $SUITE/fb/flow log -1 --format=%h)  core $(git -C $SUITE/fb/core log -1 --format=%h)"

# FindPython's artifact variables are sticky: a build dir that once configured with the wrong
# interpreter ignores a corrected -DPython_EXECUTABLE. Always reconfigure from scratch.
rm -rf "$BUILD"
cmake -S "$SUITE/fb/flow" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DPECLET_FLOW_MPI=ON \
  -DPython_EXECUTABLE="$VENV/bin/python" \
  -DPython_INCLUDE_DIR="$PYINC" \
  -DCMAKE_PREFIX_PATH="$SUITE/extern/install/$BACKEND" \
  -DMPIEXEC_EXECUTABLE="$(which mpirun)"
cmake --build "$BUILD" -j"$(nproc)"

echo
PYTHONPATH="$BUILD" python -c \
  "from peclet import flow; print('backend:', flow.execution_space, '| has_mpi:', flow.has_mpi)" \
  || echo "(import check needs a GPU for the CUDA backend; the module is built)"
echo "-> $BUILD"
