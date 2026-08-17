#!/bin/bash
# ==========================================================================================
# DEM H100 corruption probe, round 5 = round 4 done right (probe_dem4 misfired: -Xptxas in
# global CMAKE_CXX_FLAGS broke the plain-g++ TUs of the build, and `module -t avail` cannot
# see CUDA modules on other module trees).
#
# Reference: stock CUDA-12.6 GPU build FAILS the 32^3 phi=0.50 config; the CPU build passes.
#   A1) dem at -O0 (cicc + host front-end opt off; ptxas still -O3)  -> gpu_O0
#   A2) dem at -O0 plus ptxas -O0 via NVCC_APPEND_FLAGS (nvcc-only env; g++ TUs unaffected)
#                                                                     -> gpu_O0ptx
#   B)  newest CUDA found via `module spider`, separate nvidia-cuda-probe Kokkos prefix
#       (production prefix untouched), dem rebuilt against it          -> gpu_newcuda
# Build logs go to results/snellius-h100/probe5_build_*.log (tail printed on failure).
#
#   sbatch probe_dem5.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe5
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=dem-probe5-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
SCRATCH="${TMPDIR:-/tmp}"
RES="$EXDIR/results/snellius-h100"; mkdir -p "$RES"
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
declare -a SUMMARY=()

echo "=== node context ==="
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || true
echo "--- module spider CUDA (all trees):"
module -t spider CUDA 2>&1 | grep -oE "CUDA/[0-9][0-9.]*" | sort -uV || true

probe () {  # label build
  local label=$1 build=$2
  echo "=== $label (DEM_BUILD=$build) : 512^3 phi=0.50 seed=108 ==="
  if env DEM_BUILD="$build" GNX=512 GNY=512 GNZ=512 PHI=0.50 SEED=108 \
      OUT="$SCRATCH/probe5_${label}.npz" python "$EXDIR/../pack_bed.py"; then
    SUMMARY+=("PASS  $label")
  else
    SUMMARY+=("FAIL  $label")
  fi
}

build_dem () {  # builddir prefix logname extra-cmake-args...
  local bdir=$1 prefix=$2 log="$RES/probe5_build_$3.log"; shift 3
  rm -rf "$bdir"
  { cmake -S "$SUITE/dem" -B "$bdir" -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_PREFIX_PATH="$prefix" \
      -DPython_EXECUTABLE="$SUITE/flow/.venv/bin/python" -DPython_INCLUDE_DIR="$PYINC" "$@" \
    && cmake --build "$bdir" -j16; } > "$log" 2>&1
  if [ -f "$bdir/peclet/dem/__init__.py" ]; then
    echo "  (build ok: $bdir)"
  else
    echo "  BUILD FAILED -- tail of $log:"; tail -25 "$log" | sed 's/^/    /'
    return 1
  fi
}

# --- A1) front-end -O0, same CUDA 12.6 prefix ----------------------------------------------
echo "=== A1: dem at -O0 (cicc/host) ==="
if build_dem "$SUITE/dem/build_cuda_O0" "$SUITE/extern/install/nvidia-cuda" O0 \
     -DCMAKE_CXX_FLAGS="-O0"; then
  probe gpu_O0 "$SUITE/dem/build_cuda_O0"
else
  SUMMARY+=("SKIP  gpu_O0 (build failed)")
fi

# --- A2) additionally ptxas -O0, via nvcc-only env ------------------------------------------
echo "=== A2: dem at -O0 + ptxas -O0 (NVCC_APPEND_FLAGS) ==="
export NVCC_APPEND_FLAGS="-Xptxas -O0"
if build_dem "$SUITE/dem/build_cuda_O0ptx" "$SUITE/extern/install/nvidia-cuda" O0ptx \
     -DCMAKE_CXX_FLAGS="-O0"; then
  probe gpu_O0ptx "$SUITE/dem/build_cuda_O0ptx"
else
  SUMMARY+=("SKIP  gpu_O0ptx (build failed)")
fi
unset NVCC_APPEND_FLAGS

# --- B) newest CUDA toolkit from any module tree -------------------------------------------
NEWCUDA=$(module -t spider CUDA 2>&1 | grep -oE "CUDA/[0-9][0-9.]*" | sort -uV | tail -1)
echo "=== B: newest CUDA anywhere = ${NEWCUDA:-none} (stock is CUDA/12.6.0) ==="
if [ -n "$NEWCUDA" ] && [ "$NEWCUDA" != "CUDA/12.6.0" ]; then
  # Cross-tree loads may need the newer tree gate first; try a few, then the module itself.
  for tree in 2025 2025a 2024; do module load "$tree" 2>/dev/null && break; done
  if module load "$NEWCUDA" 2>&1; then
    which nvcc; nvcc --version | tail -1
    PROBE_PREFIX="$SUITE/extern/install/nvidia-cuda-probe"
    if [ ! -f "$PROBE_PREFIX/.done" ]; then
      rm -rf "$PROBE_PREFIX" "$SCRATCH/kk_build" "$SCRATCH/ax_build"
      common=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=20
              -DCMAKE_INSTALL_PREFIX="$PROBE_PREFIX" -DCMAKE_PREFIX_PATH="$PROBE_PREFIX"
              -DCMAKE_POSITION_INDEPENDENT_CODE=ON)
      { cmake -S "$SUITE/extern/src/kokkos" -B "$SCRATCH/kk_build" "${common[@]}" \
          -DKokkos_ENABLE_CUDA=ON -DKokkos_ENABLE_SERIAL=ON -DKokkos_ENABLE_CUDA_CONSTEXPR=ON \
          -DKokkos_ARCH_HOPPER90=ON -DCMAKE_CUDA_COMPILER="$(which nvcc)" \
          -DCMAKE_CUDA_ARCHITECTURES=90 \
        && cmake --build "$SCRATCH/kk_build" -j16 \
        && cmake --install "$SCRATCH/kk_build" \
        && cmake -S "$SUITE/extern/src/arborx" -B "$SCRATCH/ax_build" "${common[@]}" \
        && cmake --install "$SCRATCH/ax_build" \
        && touch "$PROBE_PREFIX/.done"; } > "$RES/probe5_build_kokkos.log" 2>&1 \
        || { echo "  PROBE-PREFIX BOOTSTRAP FAILED -- tail:"; tail -25 "$RES/probe5_build_kokkos.log" | sed 's/^/    /'; }
    fi
    if [ -f "$PROBE_PREFIX/.done" ] && build_dem "$SUITE/dem/build_cuda_probe" "$PROBE_PREFIX" newcuda; then
      probe gpu_newcuda "$SUITE/dem/build_cuda_probe"
    else
      SUMMARY+=("SKIP  gpu_newcuda (bootstrap or build failed)")
    fi
  else
    SUMMARY+=("SKIP  gpu_newcuda (cannot load $NEWCUDA from this tree)")
  fi
else
  SUMMARY+=("SKIP  gpu_newcuda (no newer CUDA on any module tree)")
fi

echo
echo "================= SUMMARY ================="
for line in "${SUMMARY[@]}"; do echo "$line"; done
cat <<'EOT'
Interpretation (stock 12.6 GPU build FAILS, CPU passes):
  gpu_O0 or gpu_O0ptx PASS -> nvcc 12.6 optimizer miscompile in dem's kernels (bisect opt level next)
  gpu_newcuda PASS         -> toolkit-version bug; rebuild the suite with that CUDA
  everything FAIL          -> UB in dem device code, sm_90-sensitive; bisect kernels with #if switches
EOT
ls -la "$SCRATCH"/probe5_*.BAD.npz 2>/dev/null && \
  cp -v "$SCRATCH"/probe5_*.BAD.npz "$RES/" 2>/dev/null || true
