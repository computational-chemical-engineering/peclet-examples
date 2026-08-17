#!/bin/bash
# ==========================================================================================
# DEM H100 corruption probe, round 4: optimizer or toolkit?
#
# probe_dem3 verdict: cpu_ref PASSES on the same machine/sources while ALL GPU variants
# fail identically regardless of solver budget -> the CUDA 12.6 + sm_90 compile path is
# implicated (workstation passes the same configs with CUDA 13.2 + sm_120). Two suspects:
#
#   A) OPTIMIZER miscompile in dem's own TU: rebuild dem with device optimization OFF
#      (-O0 -Xptxas -O0) against the SAME CUDA 12.6 prefix, re-run the failing config.
#      PASS -> nvcc/ptxas 12.6 optimization bug in dem's kernels (then bisect kernels).
#   B) TOOLKIT version: build a SEPARATE Kokkos+ArborX prefix (extern/install/
#      nvidia-cuda-probe -- the production nvidia-cuda prefix is NOT touched; running flow
#      jobs depend on it) with the newest CUDA module available, rebuild dem against it,
#      re-run. PASS -> upgrade CUDA on Snellius and rebuild; FAIL -> deeper (driver/arch).
#
# Fallback workaround regardless of outcome: pack with dem/build_omp (probe_dem3 built it;
# CPU 16-core packing is FASTER than the failing GPU runs at these N anyway).
#
#   sbatch probe_dem4.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe4
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=dem-probe4-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
SCRATCH="${TMPDIR:-/tmp}"
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
declare -a SUMMARY=()

probe () {  # label build
  local label=$1 build=$2
  echo "=== $label (DEM_BUILD=$build) : 512^3 phi=0.50 seed=108 ==="
  if env DEM_BUILD="$build" GNX=512 GNY=512 GNZ=512 PHI=0.50 SEED=108 \
      OUT="$SCRATCH/probe4_${label}.npz" python "$EXDIR/../pack_bed.py"; then
    SUMMARY+=("PASS  $label")
  else
    SUMMARY+=("FAIL  $label")
  fi
}

build_dem () {  # builddir prefix extra-cmake-args...
  local bdir=$1 prefix=$2; shift 2
  rm -rf "$bdir"
  cmake -S "$SUITE/dem" -B "$bdir" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$prefix" \
    -DPython_EXECUTABLE="$SUITE/flow/.venv/bin/python" -DPython_INCLUDE_DIR="$PYINC" \
    "$@" 2>&1 | grep -E "\[peclet\]|Kokkos|ArborX|rror" || true
  cmake --build "$bdir" -j16 2>&1 | tail -2
  [ -f "$bdir/peclet/dem/__init__.py" ]
}

# --- A) device optimization OFF, same CUDA 12.6 prefix -------------------------------------
echo "=== building dem with -O0 -Xptxas -O0 (same CUDA 12.6 prefix) ==="
if build_dem "$SUITE/dem/build_cuda_O0" "$SUITE/extern/install/nvidia-cuda" \
     -DCMAKE_CXX_FLAGS="-O0 -Xptxas -O0"; then
  probe gpu_O0 "$SUITE/dem/build_cuda_O0"
else
  SUMMARY+=("SKIP  gpu_O0 (build failed)")
fi

# --- B) newest available CUDA toolkit, separate Kokkos prefix ------------------------------
echo "=== available CUDA modules ==="
module -t avail CUDA 2>&1 | grep -E "^CUDA/" | sort -V | tee /dev/stderr | tail -1 > "$SCRATCH/newest_cuda"
NEWCUDA=$(cat "$SCRATCH/newest_cuda")
if [ -n "$NEWCUDA" ] && [ "$NEWCUDA" != "CUDA/12.6.0" ]; then
  echo "=== part B with $NEWCUDA ==="
  module load "$NEWCUDA"
  which nvcc && nvcc --version | tail -1
  PROBE_PREFIX="$SUITE/extern/install/nvidia-cuda-probe"
  if [ ! -f "$PROBE_PREFIX/.done" ]; then
    rm -rf "$PROBE_PREFIX" "$SCRATCH/kk_build" "$SCRATCH/ax_build"
    common=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=20
            -DCMAKE_INSTALL_PREFIX="$PROBE_PREFIX" -DCMAKE_PREFIX_PATH="$PROBE_PREFIX"
            -DCMAKE_POSITION_INDEPENDENT_CODE=ON)
    cmake -S "$SUITE/extern/src/kokkos" -B "$SCRATCH/kk_build" "${common[@]}" \
      -DKokkos_ENABLE_CUDA=ON -DKokkos_ENABLE_SERIAL=ON -DKokkos_ENABLE_CUDA_CONSTEXPR=ON \
      -DKokkos_ARCH_HOPPER90=ON -DCMAKE_CUDA_COMPILER="$(which nvcc)" \
      -DCMAKE_CUDA_ARCHITECTURES=90 > /dev/null \
      && cmake --build "$SCRATCH/kk_build" -j16 > /dev/null 2>&1 \
      && cmake --install "$SCRATCH/kk_build" > /dev/null \
      && cmake -S "$SUITE/extern/src/arborx" -B "$SCRATCH/ax_build" "${common[@]}" > /dev/null \
      && cmake --install "$SCRATCH/ax_build" > /dev/null \
      && touch "$PROBE_PREFIX/.done" \
      || { echo "PROBE-PREFIX BOOTSTRAP FAILED"; }
  fi
  if [ -f "$PROBE_PREFIX/.done" ] && build_dem "$SUITE/dem/build_cuda_probe" "$PROBE_PREFIX"; then
    probe gpu_newcuda "$SUITE/dem/build_cuda_probe"
  else
    SUMMARY+=("SKIP  gpu_newcuda (bootstrap or build failed)")
  fi
else
  SUMMARY+=("SKIP  gpu_newcuda (no CUDA module newer than 12.6.0)")
fi

echo
echo "================= SUMMARY ================="
for line in "${SUMMARY[@]}"; do echo "$line"; done
cat <<'EOT'
Interpretation (reference: stock CUDA-12.6 GPU build FAILS this config, CPU passes):
  gpu_O0 PASS                    -> nvcc/ptxas 12.6 OPTIMIZER miscompile in dem's kernels
  gpu_O0 FAIL + gpu_newcuda PASS -> toolkit-version bug; rebuild the suite with the newer CUDA
  both FAIL                      -> arch-specific misbehaviour surviving -O0 and toolkits:
                                    suspect UB in dem device code (sm_90-sensitive); bisect kernels
EOT
ls -la "$SCRATCH"/probe4_*.BAD.npz 2>/dev/null && \
  cp -v "$SCRATCH"/probe4_*.BAD.npz "$EXDIR/results/snellius-h100/" 2>/dev/null || true
