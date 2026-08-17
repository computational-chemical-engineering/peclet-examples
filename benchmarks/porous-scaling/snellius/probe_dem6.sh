#!/bin/bash
# ==========================================================================================
# DEM H100 corruption probe, round 6: WHICH runtime subsystem?
#
# Round 5 killed the compile-side hypotheses: -O0, -O0+ptxas-O0 and CUDA 12.9.1 all fail
# identically (and the CPU backend passes, and the forced-FUSED path passes on the
# workstation). The remaining suspects are the STATEFUL cross-step runtime optimizations of
# the solve driver, each with an env kill-switch:
#
#   graph replay  - CudaIterGraph: re-captured per step, cached executable refreshed via
#                   cudaGraphExecUpdate (parameter patching; driver-sensitive).
#                   PECLET_DEM_NO_GRAPH=1 disables -> default then takes the FUSED path.
#   fused sweeps  - software grid-barrier kernels. PECLET_DEM_NO_FUSED=1 disables; combined
#                   with NO_GRAPH this yields the PLAIN per-colour launch path.
#   incr. colour  - warm-started contact colouring carried across substeps by contact key.
#                   PECLET_DEM_NO_INCR_COLOR=1 forces a full recolour every substep.
#
# All runs: the known-failing 32^3 phi=0.50 seed=108 config, stock build_cuda.
# Decision table printed at the end. Each run ~15 s.
#
#   sbatch probe_dem6.sh
# ==========================================================================================
#SBATCH --job-name=dem-probe6
#SBATCH --partition=gpu_h100
#SBATCH --gpus=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=00:30:00
#SBATCH --output=dem-probe6-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
source "$SUITE/flow/.venv/bin/activate"
export DEM_BUILD="${DEM_BUILD:-$SUITE/dem/build_cuda}"
SCRATCH="${TMPDIR:-/tmp}"
declare -a SUMMARY=()

probe () {  # label extra-env...
  local label=$1; shift
  echo "=== $label ($*) : 512^3 phi=0.50 seed=108, stock build ==="
  if env GNX=512 GNY=512 GNZ=512 PHI=0.50 SEED=108 "$@" \
      OUT="$SCRATCH/probe6_${label}.npz" python "$EXDIR/../pack_bed.py"; then
    SUMMARY+=("PASS  $label ($*)")
  else
    SUMMARY+=("FAIL  $label ($*)")
  fi
}

probe ref_default                                     # control: expect FAIL (graph-replay path)
probe no_graph        PECLET_DEM_NO_GRAPH=1           # -> fused path
probe plain_launch    PECLET_DEM_NO_GRAPH=1 PECLET_DEM_NO_FUSED=1   # -> per-colour launches
probe fused_forced    PECLET_DEM_FUSED=1              # fused even though graphs available
probe full_recolor    PECLET_DEM_NO_INCR_COLOR=1      # graphs on, incremental colouring off

echo
echo "================= SUMMARY ================="
for line in "${SUMMARY[@]}"; do echo "$line"; done
cat <<'EOT'
Interpretation:
  plain_launch PASS + no_graph PASS + ref FAIL     -> CUDA-graph replay path is the bug
      (workaround everywhere: PECLET_DEM_NO_GRAPH=1; then chase cudaGraphExecUpdate)
  plain_launch PASS + no_graph FAIL                -> fused barrier ALSO bad on H100 (two bugs
      or shared substrate); workaround: NO_GRAPH=1 + NO_FUSED=1
  full_recolor PASS + ref FAIL                     -> incremental-colouring carry is the bug
  everything FAIL                                  -> in the kernels themselves after all;
      bisect narrowphase/solver with #if next
EOT
ls -la "$SCRATCH"/probe6_*.BAD.npz 2>/dev/null && \
  cp -v "$SCRATCH"/probe6_*.BAD.npz "$EXDIR/results/snellius-h100/" 2>/dev/null || true
