#!/bin/bash
# ==========================================================================================
# DEM H100 corruption probe, round 2: MAP THE FAILURE BOUNDARY.
#
# probe_dem.sh established the corruption is DETERMINISTIC on H100 (6/6, phi_voxel 0.405
# vs 0.50) while the same seeds/configs pack perfectly on an sm_120 workstation card, with
# max_asleep=0 and the pair buffer auto-grown (solve_driver.hpp findCollisionsGrow), so the
# simple explanations are dead. Known so far: box 32x32x32 (N=3911) and 64x32x32 (N=7823)
# fail; 16^3 (489), 32x16x16 (978), 32x32x16 (1956), 64x64x32 (15646) pack fine.
#
# This job walks phi (=> N at fixed box) and box size across that gap, plus seed and
# aspect-ratio controls -- each attempt ~10 s and self-diagnosing via pack_bed's voxel gate.
# On failure pack_bed now saves the corrupted state to *.BAD.npz for forensics.
# Read the SUMMARY table at the end of dem-probe2-<jobid>.out:
#   - a sharp phi/N threshold independent of seed  -> capacity/threshold-style bug
#   - failure tracking box GEOMETRY, not N         -> periodic-ghost / binning suspect
#   - seed-dependent scatter                       -> dynamics/race
#
#   sbatch probe_dem2.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe2
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=00:45:00
#SBATCH --output=dem-probe2-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
export DEM_BUILD="${DEM_BUILD:-$SUITE/dem/build_cuda}"
SCRATCH="${TMPDIR:-/tmp}"
declare -a SUMMARY=()

probe () {  # label gnx gny gnz phi seed
  local label=$1 gnx=$2 gny=$3 gnz=$4 phi=$5 seed=$6
  echo "=== $label : grid ${gnx}x${gny}x${gnz} phi=$phi seed=$seed ==="
  if env GNX=$gnx GNY=$gny GNZ=$gnz PHI=$phi SEED=$seed \
      OUT="$SCRATCH/probe2_${label}.npz" python "$EXDIR/../pack_bed.py"; then
    SUMMARY+=("PASS  $label (${gnx}x${gny}x${gnz} phi=$phi seed=$seed)")
  else
    SUMMARY+=("FAIL  $label (${gnx}x${gny}x${gnz} phi=$phi seed=$seed)")
  fi
}

# 1) phi sweep at the failing 32^3 box (seed 108): N = 2347..3911. Where does it break?
probe phi030 512 512 512 0.30 108
probe phi040 512 512 512 0.40 108
probe phi045 512 512 512 0.45 108
probe phi048 512 512 512 0.48 108
probe phi050 512 512 512 0.50 108     # known FAIL (reference)

# 2) box sweep at phi=0.50, cubic: box 24, 28, 30 (N = 1650, 2620, 3222) vs known-bad 32.
probe box24 384 384 384 0.50 108
probe box28 448 448 448 0.50 108
probe box30 480 480 480 0.50 108

# 3) seed control at the failing config: is it seed-independent (deterministic in CONFIG)?
probe seed9  512 512 512 0.50 9
probe seed42 512 512 512 0.50 42

# 4) aspect control: nearly the same N as the failing 32^3 (box 45x45x16 R-units = 32400 R^3,
#    N ~ 3868 vs 3911) but flat -- separates particle COUNT from box geometry.
probe flat 720 720 256 0.50 108

# 5) known-good control re-run (32x32x16, N=1956): confirms the harness itself.
probe good104 512 512 256 0.50 104

echo
echo "================= SUMMARY ================="
for line in "${SUMMARY[@]}"; do echo "$line"; done
echo "BAD specimens (if any): $SCRATCH/probe2_*.BAD.npz -- copy them off the node NOW"
echo "(node-local TMPDIR is wiped at job end):"
ls -la "$SCRATCH"/probe2_*.BAD.npz 2>/dev/null && \
  cp -v "$SCRATCH"/probe2_*.BAD.npz "$EXDIR/results/snellius-h100/" 2>/dev/null || true
