#!/bin/bash
# ==========================================================================================
# DEM broadphase-corruption probe (see results/packings incident, 2026-08-14): on two of six
# Snellius H100 packing runs (seeds 108/116) the contact list silently dropped most pairs --
# spheres grew through each other (phi_voxel 0.40 instead of 0.50) while get_max_overlap()
# stayed under the gate (it only sees TRACKED contacts). The same seeds/configs pack
# perfectly on the workstation GPU.
#
# This job re-runs those two packs 3x each on one H100. pack_bed.py now carries an
# independent voxelized union-fraction gate, so each attempt is self-diagnosing:
#   PASS  = "[pack] independent voxel solid fraction=0.5..." and an [out] line
#   REPRO = "FATAL: voxel fraction ... spheres are interpenetrating" (exit 1, no npz)
# 3x PASS on both seeds -> the corruption was flaky (node/driver-level).
# Any REPRO       -> deterministic dem-on-H100 bug, and this is the reproducer.
# Afterwards it runs dem's ctest suite on the H100, if the build registers tests.
#
#   sbatch probe_dem.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=00:30:00
#SBATCH --output=dem-probe-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
export DEM_BUILD="${DEM_BUILD:-$SUITE/dem/build_cuda}"
SCRATCH="${TMPDIR:-/tmp}"

fail=0
probe () {  # gnx gny gnz seed attempt
  echo "=== pack probe seed=$4 ${1}x${2}x${3} attempt $5 ==="
  if env GNX=$1 GNY=$2 GNZ=$3 SEED=$4 OUT="$SCRATCH/probe_s$4_$5.npz" \
      python "$EXDIR/../pack_bed.py"; then
    echo "--- attempt $5: PASS"
  else
    echo "--- attempt $5: FAILED (corruption reproduced, or crash -- see above)"
    fail=1
  fi
}

for i in 1 2 3; do probe  512 512 512 108 "$i"; done
for i in 1 2 3; do probe 1024 512 512 116 "$i"; done

echo "=== dem ctest on H100 ==="
ctest --test-dir "$DEM_BUILD" --output-on-failure || echo "(no ctests registered, or failures above)"

echo
if [ "$fail" = 1 ]; then
  echo "VERDICT: corruption REPRODUCED on H100 -- deterministic dem bug, reproducer secured."
else
  echo "VERDICT: all probes clean -- the 2026-08-14 corruption was flaky (node/driver-level);"
  echo "         the voxel gates in pack_bed.py / spheres_bench.py remain the defense."
fi
