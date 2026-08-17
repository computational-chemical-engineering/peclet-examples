#!/bin/bash
# ==========================================================================================
# DEM H100 corruption probe, round 7: compute-sanitizer on the failing kernels.
#
# probe_dem6: ALL five execution modes fail identically (graph replay / fused barriers /
# plain launches / full recolor) -> the fault is inside the device kernels themselves.
# Combined profile (CPU passes; -O0 and CUDA 12.9 fail; deterministic per machine+config;
# non-monotone in N) fits an intra-kernel race or an out-of-bounds access whose victim
# memory differs between machines' allocation layouts. colorKey collisions are excluded
# (unique index in the low word).
#
# This round runs NVIDIA compute-sanitizer (no source changes) on the failing config:
#   memcheck   - OOB / misaligned global accesses     (primary suspect)
#   initcheck  - reads of uninitialized global memory (second suspect)
#   racecheck  - shared-memory data races             (completeness)
# plus a memcheck run of a PASSING config (s104) as the differential control.
# ~10-50x slowdown on an 8.5s run -> minutes each. Full logs are the deliverable.
#
#   sbatch probe_dem7.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe7
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=01:30:00
#SBATCH --output=dem-probe7-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
export DEM_BUILD="${DEM_BUILD:-$SUITE/dem/build_cuda}"
SCRATCH="${TMPDIR:-/tmp}"
RES="$EXDIR/results/snellius-h100"; mkdir -p "$RES"
SAN=$(which compute-sanitizer) || { echo "FATAL: compute-sanitizer not on PATH"; exit 1; }
echo "sanitizer: $SAN"

run_san () {  # tool label gnx gny gnz seed
  local tool=$1 label=$2 gnx=$3 gny=$4 gnz=$5 seed=$6
  local log="$RES/probe7_${tool}_${label}.log"
  echo "=== $tool on $label (${gnx}x${gny}x${gnz} seed=$seed) -> $(basename $log) ==="
  env GNX=$gnx GNY=$gny GNZ=$gnz PHI=0.50 SEED=$seed OUT="$SCRATCH/probe7_${label}.npz" \
    "$SAN" --tool "$tool" --error-exitcode 99 --print-limit 50 \
    python "$EXDIR/../pack_bed.py" > "$log" 2>&1
  local rc=$?
  # sanitizer verdict + the pack's own gate, independently
  local nerr; nerr=$(grep -cE "^========= (Invalid|Uninitialized|Race|ERROR|Error)" "$log" || true)
  grep -m1 "ERROR SUMMARY" "$log" || true
  grep -m1 "independent voxel solid fraction" "$log" || true
  echo "    exit=$rc sanitizer-flagged-lines=$nerr"
  grep -m3 -A6 "^========= Invalid\|^========= Uninitialized\|^========= Race" "$log" | sed 's/^/    /'
}

# Failing config, all three tools:
run_san memcheck  s108 512 512 512 108
run_san initcheck s108 512 512 512 108
run_san racecheck s108 512 512 512 108
# Passing config, memcheck (differential control -- a latent error that fires in both
# still needs fixing; an error ONLY in s108 is the smoking gun):
run_san memcheck  s104 512 512 256 104

echo
echo "Deliverable: the four probe7_*.log files in snellius/results/snellius-h100/ --"
echo "copy them back with the .out; the first 'Invalid ... of size N' block names the"
echo "guilty kernel + access."
