#!/bin/bash
# ==========================================================================================
# Porous-bed REFINE weak scaling on Snellius gpu_h100 — ONE fixed physical packing (16^3
# R-units, seed 100 — the committed, workstation-validated bed), grid refined with the GPU
# count. Cells/GPU
# varies (3-D refinement cannot hold it), so weak efficiency reads from PER-GPU throughput.
# Physics payoff: k(N) -> k_inf per IBM (Richardson + observed order) and the cut-cell/ghost
# k_inf cross-check. The sphere radius spans 16 -> 64 cells across the ladder.
#
# Argument 1 = GPU count (1,2,4,8,16,32), or empty = sweep. Argument 2 = optional result tag.
#   sbatch --nodes=1 spheres_refine_gpu.sh 1     # N=256
#   sbatch --nodes=1 spheres_refine_gpu.sh 2     # N=384
#   sbatch --nodes=1 spheres_refine_gpu.sh 4     # N=512
#   sbatch --nodes=2 spheres_refine_gpu.sh 8     # N=640
#   sbatch --nodes=4 spheres_refine_gpu.sh 16    # N=768
#   sbatch --nodes=8 spheres_refine_gpu.sh 32    # N=1024
# ==========================================================================================
#SBATCH --job-name=por-ref
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=01:00:00
#SBATCH --output=por-ref-%j.out
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

# The ONE physical bed: box 16^3 R-units, phi 0.50, seed 100 — the COMMITTED,
# workstation-validated bed in ../results/packings (found automatically; re-packed with the
# same seed only if missing). Refinement resamples it; RCELLS scales with N.
export PHI=0.50 NSTEPS=25 WARMUP=5 MARCH_TOL=1e-5 MARCH_MAX=400
SEED=100
NPZ="$PACKS/packing_256x256x256_r16_phi${PHI}_s${SEED}.npz"

# rung -> N levels (levels hold the coarsest grid at 8-12 cells/axis; the agglomerated bottom
# solves it exactly, so iterations should be flat across the whole ladder)
cfg_of () { case $1 in
  1)  echo 256 6;; 2)  echo 384 6;; 4)  echo 512 7;;
  8)  echo 640 7;; 16) echo 768 7;; 32) echo 1024 8;;
  *) return 1;; esac; }

MAXN=$(( SLURM_NNODES * 4 ))

[ -f "$NPZ" ] || env GNX=256 GNY=256 GNZ=256 RCELLS=16 SEED=$SEED OUT="$NPZ" \
    srun --ntasks=1 --gpus-per-task=1 "$VENV/bin/python" "$EXDIR/../pack_bed.py" \
    >> "$RES/pack.log" 2>&1 || { echo "[FATAL] packing failed (see $RES/pack.log)"; exit 1; }

run_one () {  # N ibm out extra-env...
  local N=$1 ibm=$2 out=$3; shift 3
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  read -r G LV <<< "$(cfg_of $N)" || { echo "[FATAL] no cfg for N=$N"; return 1; }
  echo "======= N=$N $ibm : ${G}^3 = $(( G * G * G / 1000000 ))M, levels=$LV  ($out) ======="
  env GNX=$G GNY=$G GNZ=$G MGLEVELS=$LV PACK="$NPZ" IBM=$ibm LABEL="snellius-h100" \
      OUT="$RES/$out" "$@" \
    srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXDIR/../spheres_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(perf|march|sdf)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED N=$N $ibm] (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|out of memory|assert|FATAL" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

ARG="${1:-}"; TAG="${2:+_${2}}"
if [ -n "$ARG" ]; then
  [ "$ARG" -le "$MAXN" ] || { echo "FATAL: N=$ARG needs $(( (ARG+3)/4 )) nodes, allocated $SLURM_NNODES" >&2; exit 1; }
  run_one "$ARG" cutcell "refine_np${ARG}_cutcell${TAG}.json"
  run_one "$ARG" ghost   "refine_np${ARG}_ghost${TAG}.json"
else
  for N in 1 2 4 8 16 32; do
    [ "$N" -le "$MAXN" ] || continue
    run_one $N cutcell "refine_np${N}_cutcell${TAG}.json"
    run_one $N ghost   "refine_np${N}_ghost${TAG}.json"
  done
fi
echo "done -> $RES"
