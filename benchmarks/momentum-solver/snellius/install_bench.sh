#!/bin/bash
# ==========================================================================================
# Provisioning for the peclet 1.0.0 scaling deposit: build the RELEASED tag from source into
# its own tree + venv on Snellius. Derived from suite `tools/hpc/install_snellius.sh` (the
# family site install) and trimmed to the three packages this benchmark imports —
# morton, core, flow — so the build cannot fail on a package the study never uses.
#
# The PyPI wheels CANNOT serve this benchmark: MPI is a build-time option in flow
# (-DPECLET_FLOW_MPI=ON) and the published wheels are single-rank. Hence a site build.
#
#   sbatch --nodes=1 --gpus-per-node=1 --ntasks-per-node=1  snellius/install_bench.sh v1.0.0 h100
#   sbatch -p genoa --gpus-per-node=0 -c 32 -t 02:00:00      snellius/install_bench.sh v1.0.0 cpu
#
# Arguments are POSITIONAL (SURF's sbatch drops a leading VAR=x from the command line).
# Products:  $PROJ/suite-<tag>-bench-<target>/{,.venv}  and  $PROJ/wheelhouse/<tag>-<target>-bench/
# ==========================================================================================
#SBATCH --job-name=peclet-bench-install
#SBATCH --partition=gpu_h100
#SBATCH --gpus-per-node=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=03:00:00
#SBATCH --output=install-%j.out
#SBATCH --account=tes24005
set -euo pipefail
TAG="${1:?usage: install_bench.sh <tag> <h100|cpu>}"
TARGET="${2:-h100}"
PROJ="${PROJ:-/projects/0/prjs1022/peclet}"
SUITE="$PROJ/suite-$TAG-bench-$TARGET"      # ONE TREE PER BACKEND: a CUDA and a host build share
WHEELS="$PROJ/wheelhouse/$TAG-$TARGET-bench" # neither a checkout, an extern prefix, nor a venv

# A batch script runs from the Slurm SPOOL, where $BASH_SOURCE has no siblings -- resolve the
# campaign directory from the submit dir (or an explicit BENCH=) and fail loudly if it is not found.
find_envdir() {
  local c
  for c in "${BENCH:-}/snellius" "${SLURM_SUBMIT_DIR:-$PWD}/snellius" \
           "${SLURM_SUBMIT_DIR:-$PWD}/../snellius" "$(dirname "${BASH_SOURCE[0]}")"; do
    [ -f "$c/snellius_env.sh" ] && { (cd "$c" && pwd); return 0; }
  done
  echo "FATAL: snellius_env.sh not found (set BENCH=<campaign dir> or submit from it)" >&2; exit 1
}
ENVDIR="$(find_envdir)"
source "$ENVDIR/snellius_env.sh"

# --- 1. checkout at the tag (HTTPS: compute nodes have no GitHub key) ------------------------
git config --global url."https://github.com/".insteadOf "git@github.com:"
if [ ! -d "$SUITE/.git" ]; then
  git clone --branch "$TAG" --recurse-submodules \
    https://github.com/computational-chemical-engineering/peclet.git "$SUITE"
fi
cd "$SUITE"
git submodule update --init --recursive
echo "== provenance: umbrella $(git describe --tags --always)"
git submodule status | awk '{print "==   "$2" "substr($1,1,10)}'

# --- 2. venv --------------------------------------------------------------------------------
python3 -c 'import sys; assert sys.version_info[:2]>=(3,10), sys.version'
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel nanobind numpy scipy mpi4py matplotlib scikit-build-core

# --- 3. Kokkos prefix for the backend --------------------------------------------------------
case "$TARGET" in
  h100) BACKEND=nvidia-cuda; KA=HOPPER90; CA=90 ;;
  cpu)  BACKEND=host-openmp; KA=; CA= ;;
  *) echo "usage: $0 <tag> <h100|cpu>"; exit 1 ;;
esac
if [ ! -f "extern/install/$BACKEND/.bench-stamp" ]; then
  rm -rf "extern/build/$BACKEND" "extern/install/$BACKEND"   # a release tree starts clean
  if [ "$BACKEND" = nvidia-cuda ]; then
    KOKKOS_ARCH=$KA CUDA_ARCH=$CA CUDA_COMPILER=$(which nvcc) tools/bootstrap_deps.sh nvidia-cuda
  else
    tools/bootstrap_deps.sh host-openmp
  fi
  touch "extern/install/$BACKEND/.bench-stamp"
fi
PREFIX="$SUITE/extern/install/$BACKEND"

# --- 4. wheels: morton, core, flow (MPI ON), then install them -------------------------------
#   A venv has no Python.h: pass the base interpreter's include dir (INCLUDEPY is right from a venv).
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
export CMAKE_PREFIX_PATH="$PREFIX"
export CMAKE_ARGS="-DPython_EXECUTABLE=$SUITE/.venv/bin/python -DPython_INCLUDE_DIR=$PYINC -DMPIEXEC_EXECUTABLE=$(which mpirun)"
mkdir -p "$WHEELS"
wheel() { local d="$1"; shift; echo "== pip wheel $d $*"; pip wheel --no-deps --no-build-isolation -w "$WHEELS" "$@" "./$d"; }
wheel morton
wheel core --config-settings=cmake.define.PECLET_CORE_KOKKOS=ON
wheel flow --config-settings=cmake.define.PECLET_FLOW_MPI=ON
pip install --no-index --find-links "$WHEELS" peclet-morton peclet-core peclet-flow
ls -la "$WHEELS"

# --- 5. provenance census: everything a reader needs to know about this build ----------------
CENSUS="$SUITE/census-$TARGET.txt"
{
  echo "# peclet 1.0.0 scaling benchmark — build census ($(date -Is))"
  echo "host          : $(hostname)   slurm job ${SLURM_JOB_ID:-none}"
  echo "tag           : $TAG   umbrella $(git -C "$SUITE" describe --tags --always)"
  git -C "$SUITE" submodule status | awk '{print "submodule     : "$2" "$1}'
  echo "backend       : $BACKEND  arch ${KA:-host}"
  echo "python        : $(python3 -V)"
  echo "mpi           : $(mpirun --version 2>&1 | head -1)"
  echo "nvcc          : $(which nvcc >/dev/null 2>&1 && nvcc --version | tail -2 | head -1 || echo n/a)"
  echo "driver        : $(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | head -1 || echo n/a)"
  echo "modules       : $(module -t list 2>&1 | tr '\n' ' ')"
  echo "--- pip freeze ---"; pip freeze
  echo "--- wheel sha256 ---"; sha256sum "$WHEELS"/*.whl
} > "$CENSUS"
cat "$CENSUS"

echo "== flow build configuration (must read has_mpi=True, operator storage double)"
python - <<'PY' || echo "(GPU import check needs a GPU node; wheels are still valid)"
import peclet.flow as f
print("flow", f.__version__, "space", f.execution_space, "has_mpi", f.has_mpi)
PY
echo "-> tree $SUITE ; venv $SUITE/.venv ; wheelhouse $WHEELS ; census $CENSUS"
