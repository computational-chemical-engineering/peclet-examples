#!/bin/bash
# ==========================================================================================
# Collocated second-order A/B on Snellius gpu_h100 — which collocated projection should carry
# the AMR work?  ONE fixed physical bed (the committed 16^3 R-unit, phi 0.50, seed-100 packing),
# refined over R = 5..32 cells per sphere radius, four solvers on identical geometry:
#
#   stag_cutcell   flow.Solver        aperture cut-cell     <- the REFERENCE (2nd order, k_inf)
#   col_mode0      SolverColocated    aperture, plain map   <- the known 1st-order baseline
#   col_mode9      SolverColocated    aperture + gpCenterGrad (set_face_interp(9))
#   col_ghost      SolverColocated    directional ghost projection
#
# The question this answers: on a BED (not a single smooth sphere) does mode 9 hold a second-order
# -- or at least monotone, small -- error against the staggered reference at cut-cell iteration
# counts, while the ghost projection over-carries the throats at ~6x the cost?  The coarse rungs
# (R=5,6,8) ARE the under-resolved tight-throat regime; the fine rungs give the observed order.
#
# Argument 1 = R (5,6,8,12,16,24,32), or empty = every rung the allocation can hold.
# Argument 2 = optional result tag.
#   sbatch --nodes=1 --time=01:00:00 collocated_ab_gpu.sh 5     # 80^3   1 GPU
#   sbatch --nodes=1 --time=01:00:00 collocated_ab_gpu.sh 6     # 96^3   1 GPU
#   sbatch --nodes=1 --time=01:00:00 collocated_ab_gpu.sh 8     # 128^3  1 GPU
#   sbatch --nodes=1 --time=02:00:00 collocated_ab_gpu.sh 12    # 192^3  1 GPU
#   sbatch --nodes=1 --time=03:00:00 collocated_ab_gpu.sh 16    # 256^3  1 GPU
#   sbatch --nodes=1 --time=04:00:00 collocated_ab_gpu.sh 24    # 384^3  2 GPUs
#   sbatch --nodes=1 --time=06:00:00 collocated_ab_gpu.sh 32    # 512^3  4 GPUs
# Argument 3 = bed: phi050 (default) | phi060 (the dense tight-throat bed):
#   sbatch --nodes=1 --gpus-per-node=1 --ntasks-per-node=1 collocated_ab_gpu.sh 8 "" phi060
# ==========================================================================================
#SBATCH --job-name=col-ab
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=col-ab-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
DEM_BUILD="${DEM_BUILD:-$SUITE/dem/build_cuda}"
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}" DEM_BUILD
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI="${GPU_AWARE:-1}"
RES="$EXDIR/results/snellius-h100"; PACKS="$EXDIR/../results/packings"
mkdir -p "$RES" "$PACKS"

# Tight steady state: the discriminating differences are 0.02-0.3 % in k, so the march must be
# converged well below that. Phase A (25 fixed steps) is kept only for the per-step cost numbers.
export PHI=0.50 NSTEPS=25 WARMUP=5 MARCH_TOL=1e-6 MARCH_MAX=800
SEED=100

# R -> grid, MG levels (coarsest axis 8-12 cells: the agglomerated bottom solves it exactly),
# GPUs (ghost carries a worst-case-sized overlay, ~1.1 GB per Mcell -- keep <= ~40 GB/GPU)
cfg_of () { case $1 in
   5) echo  80 4 1;;  6) echo  96 4 1;;   8) echo 128 5 1;;  12) echo 192 5 1;;
  16) echo 256 6 1;; 24) echo 384 6 2;;  32) echo 512 7 4;;
  *) return 1;; esac; }

MAXN=$(( SLURM_NNODES * 4 ))

run_one () {  # R variant grid ibm faceinterp
  local R=$1 var=$2 grid=$3 ibm=$4 fi=$5
  local out="${PREFIX}_R${R}_${var}${TAG}.json"
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  read -r G LV NP <<< "$(cfg_of $R)" || { echo "[FATAL] no cfg for R=$R"; return 1; }
  [ "$NP" -le "$MAXN" ] || { echo "[FATAL] R=$R needs $NP GPUs, allocated $MAXN" >&2; return 1; }
  echo "======= R=$R $var : ${G}^3 = $(( G * G * G / 1000000 ))M on $NP GPU(s), levels=$LV ======="
  env GNX=$G GNY=$G GNZ=$G MGLEVELS=$LV PACK="$NPZ" GRID=$grid IBM=$ibm FACEINTERP=$fi \
      LABEL="snellius-h100" OUT="$RES/$out" \
    srun --mpi=pmix --ntasks=$NP --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXDIR/../spheres_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(perf|march|sdf)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED R=$R $var] (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|out of memory|assert|FATAL" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

run_rung () {  # R
  run_one "$1" stag_cutcell staggered  cutcell 0
  run_one "$1" col_mode0    collocated cutcell 0
  run_one "$1" col_mode9    collocated cutcell 9
  run_one "$1" col_ghost    collocated ghost   0
  # The Basilisk embed.h line (true-normal wall gradient): the candidate for removing the
  # collocated accuracy ceiling. 6 = embed momentum + plain projection + openness-weighted cell
  # correction; 7 = 6 with the wall-aware constraint.
  run_one "$1" col_embed6   collocated cutcell 6
  run_one "$1" col_embed7   collocated cutcell 7
}

# Argument 3 selects the BED. Both are 16^3 R-unit boxes, so the R -> grid table is shared.
#   phi050 (default) the phi=0.50 seed-100 bed        -> colcmp_R*      (the shipped ladder)
#   phi060           the phi=0.60 seed-3 dense bed    -> colcmp060_R*   (tight throats: the
#                    median nearest-neighbour surface gap is 0.0002 R against 0.0107 R at
#                    phi=0.50, i.e. the spheres are AT contact -- the regime where the ghost
#                    projection was documented to over-carry the throats)
ARG="${1:-}"; TAG="${2:+_${2}}"; BED="${3:-phi050}"
case "$BED" in
  phi050) NPZ="$PACKS/packing_256x256x256_r16_phi0.50_s100.npz"; PREFIX=colcmp;;
  phi060) NPZ="$PACKS/packing_256x256x256_r16_phi0.60_s3.npz";   PREFIX=colcmp060;;
  *) echo "FATAL: unknown bed '$BED' (phi050|phi060)" >&2; exit 1;;
esac
[ -f "$NPZ" ] || { echo "FATAL: bed $NPZ is missing (pack_bed.py, or git checkout the committed one)" >&2; exit 1; }
echo "bed: $NPZ  ->  ${PREFIX}_R*"

if [ -n "$ARG" ]; then
  run_rung "$ARG"
else
  for R in 5 6 8 12 16 24 32; do
    read -r _ _ NP <<< "$(cfg_of $R)"; [ "$NP" -le "$MAXN" ] || continue
    run_rung "$R"
  done
fi
echo "done -> $RES"
