#!/bin/bash
# ==========================================================================================
# S2 probe of the collocated accuracy ceiling (flow/doc/collocated_accuracy_ceiling.md §5):
# dt sweep at a plateau rung. If the steady k of the collocated gauge-exact scheme depends on
# DT, the incremental-rotational pressure accumulation (S2) is indicted AND design constraint
# C2 (dt-independent steady states) is violated. dt-fair stopping: MARCH_TOL=1e-8 with
# CHECK_EVERY scaled inversely with DT so every run stops on the same physical-time criterion.
#
#   sbatch --time=03:00:00 dtsweep_gpu.sh 16          # 256^3 phi=0.60 bed, 1 H100
#   sbatch --time=04:00:00 dtsweep_gpu.sh 24          # 384^3, still 1 GPU (mem permitting)
# ==========================================================================================
#SBATCH --job-name=dtsweep
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --time=03:00:00
#SBATCH --output=dtsweep-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0
RES="$EXDIR/results/snellius-h100"; PACKS="$EXDIR/../results/packings"
mkdir -p "$RES"

R="${1:-16}"
case $R in
  12) G=192; LV=5;; 16) G=256; LV=6;; 24) G=384; LV=6;;
  *) echo "FATAL: no cfg for R=$R" >&2; exit 1;;
esac
NPZ="$PACKS/packing_256x256x256_r16_phi0.60_s3.npz"
[ -f "$NPZ" ] || { echo "FATAL: bed $NPZ missing" >&2; exit 1; }

run () { # variant grid faceinterp dt check max
  local var=$1 grid=$2 fi=$3 dt=$4 chk=$5 mx=$6
  local out="$RES/dtsweep060_R${R}_${var}_dt${dt}.json"
  [ -f "$out" ] && { echo "[skip] $out"; return; }
  echo "=== R=$R $var DT=$dt (check=$chk max=$mx) ==="
  env GNX=$G GNY=$G GNZ=$G MGLEVELS=$LV PACK="$NPZ" GRID=$grid IBM=cutcell FACEINTERP=$fi \
      DT=$dt MARCH_TOL=1e-8 CHECK_EVERY=$chk MARCH_MAX=$mx NSTEPS=5 WARMUP=2 \
      LABEL="snellius-h100-dtsweep" OUT="$out" \
    srun --mpi=pmix --ntasks=1 --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXDIR/../spheres_bench.py" > "${out%.json}.log" 2>&1 \
    && grep -E "^\[march" "${out%.json}.log" | tail -2 \
    || { echo "  [FAILED $var dt=$dt]"; grep -m1 -A6 Traceback "${out%.json}.log" | sed 's/^/    /'; }
}

run col_mode9 collocated 9 600 2 600
run col_mode9 collocated 9 60 20 3000
run col_mode9 collocated 9 6 200 20000
run stag      staggered  0 600 2 600
run stag      staggered  0 60 20 3000
run stag      staggered  0 6 200 20000
echo "done -> $RES"
