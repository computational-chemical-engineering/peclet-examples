#!/bin/bash
# ==========================================================================================
# DEM H100 corruption probe, round 3: WHAT breaks -- dynamics budget, or the CUDA build?
#
# probe_dem2 mapped the failure (box 30-32 R-units cubic at phi>=0.45 EXCEPT phi=0.48;
# seed-independent; equal-N flat box passes) and the specimens show a UNIFORM bulk failure
# (96% of particles in deep overlaps, no boundary/index structure), with the solve cost
# elevated 2-3x from the start. Source reading: once contact degree exceeds the 62-colour
# mask cap, contacts fall to a soft Jacobi fallback and the tangle is irrecoverable -- that
# is the amplifier. This round hunts the SEED of the runaway with two families:
#
#   A) solver-budget knobs at the failing config (H100 GPU): more XPBD iterations, smaller
#      growth per step. If a bigger budget fixes it -> dynamical runaway that sm_120 happens
#      to survive; if no knob helps -> points at the build/toolchain.
#   B) SAME machine, SAME sources, CPU OpenMP backend: bootstraps extern/install/host-openmp
#      (offline; extern/src is already populated), builds dem/build_omp, re-runs the failing
#      config on the CPU. FAIL on CPU too -> not a GPU/arch bug (machine env / build config);
#      PASS on CPU -> narrows to the CUDA 12.6 + sm_90 compile path (workstation passes with
#      CUDA 13.2 + sm_120).
#
# Every attempt is self-diagnosing (pack_bed voxel gate + .BAD.npz specimens). Read the
# SUMMARY at the end of dem-probe3-<jobid>.out.
#
#   sbatch probe_dem3.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe3
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=01:30:00
#SBATCH --output=dem-probe3-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
SCRATCH="${TMPDIR:-/tmp}"
declare -a SUMMARY=()

probe () {  # label build extra-env...
  local label=$1 build=$2; shift 2
  echo "=== $label (DEM_BUILD=$build $*) : 512^3 phi=0.50 seed=108 ==="
  if env DEM_BUILD="$build" GNX=512 GNY=512 GNZ=512 PHI=0.50 SEED=108 "$@" \
      OUT="$SCRATCH/probe3_${label}.npz" python "$EXDIR/../pack_bed.py"; then
    SUMMARY+=("PASS  $label ($*)")
  else
    SUMMARY+=("FAIL  $label ($*)")
  fi
}

GPU="$SUITE/dem/build_cuda"

# --- A) solver-budget knobs on the H100 (reference config is a known 6/6 FAIL) ------------
probe ref        "$GPU"
probe iters200   "$GPU" ITERS=200
probe iters400   "$GPU" ITERS=400
probe dt0005     "$GPU" DT=0.005
probe rate015    "$GPU" RATE=0.15
probe gentle     "$GPU" DT=0.005 ITERS=200

# --- B) CPU OpenMP control on THIS machine -------------------------------------------------
if [ ! -d "$SUITE/extern/install/host-openmp" ]; then
  echo "=== bootstrapping host-openmp Kokkos+ArborX (offline, reuses extern/src) ==="
  (cd "$SUITE" && tools/bootstrap_deps.sh host-openmp) || echo "BOOTSTRAP FAILED"
fi
if [ ! -f "$SUITE/dem/build_omp/peclet/dem/__init__.py" ]; then
  echo "=== building dem host-openmp module ==="
  PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
  rm -rf "$SUITE/dem/build_omp"
  cmake -S "$SUITE/dem" -B "$SUITE/dem/build_omp" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$SUITE/extern/install/host-openmp" \
    -DPython_EXECUTABLE="$SUITE/flow/.venv/bin/python" -DPython_INCLUDE_DIR="$PYINC" \
    2>&1 | grep -E "peclet|Kokkos|ArborX|Error|error" || true
  cmake --build "$SUITE/dem/build_omp" -j16 2>&1 | tail -3
fi
export OMP_NUM_THREADS=16 OMP_PROC_BIND=spread OMP_PLACES=threads
probe cpu_ref    "$SUITE/dem/build_omp"

echo
echo "================= SUMMARY ================="
for line in "${SUMMARY[@]}"; do echo "$line"; done
cat <<'EOT'
Interpretation:
  ref FAIL + any knob PASS + cpu_ref PASS  -> dynamical runaway; budget-sensitive; arch tips it
  ref FAIL + all knobs FAIL + cpu_ref PASS -> CUDA 12.6/sm_90 build path implicated
  ref FAIL + cpu_ref FAIL                  -> not a GPU bug: machine env / common build config
EOT
ls -la "$SCRATCH"/probe3_*.BAD.npz 2>/dev/null && \
  cp -v "$SCRATCH"/probe3_*.BAD.npz "$EXDIR/results/snellius-h100/" 2>/dev/null || true
