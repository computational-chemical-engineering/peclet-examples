#!/bin/bash
# ==========================================================================================
# Porous-bed UPSCALE weak scaling on Snellius gpu_h100 — 256^3 cells/GPU fixed, the domain
# (and the DEM packing in it) grows with N. Each rung packs its own bed (seeded per rung,
# seconds on one GPU) then runs the flow benchmark, cut-cell AND ghost IBM.
#
# Argument 1 = the GPU count to measure (queue-parallel safe), or 'levers' for the ablation at
# the allocated max, or empty = sweep all that fit. Argument, not env — SURF sbatch drops
# leading env vars.  Argument 2 = optional result tag (REQUIRED after any solver change:
# run_one skips existing JSONs).
#   sbatch --nodes=1 spheres_weak_gpu.sh 1
#   sbatch --nodes=1 spheres_weak_gpu.sh 2
#   sbatch --nodes=1 spheres_weak_gpu.sh 4
#   sbatch --nodes=2 spheres_weak_gpu.sh 8
#   sbatch --nodes=4 spheres_weak_gpu.sh 16
#   sbatch --nodes=8 spheres_weak_gpu.sh 32
#   sbatch --nodes=8 spheres_weak_gpu.sh levers   # smoothed-bottom / host-staged at max N
# ==========================================================================================
#SBATCH --job-name=por-weak
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=01:00:00
#SBATCH --output=por-weak-%j.out
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

# rung -> grid: 256^3/GPU, doubling x,y,z in turn (blocks tile exactly -> imbalance 1.000)
grid_of () { case $1 in
  1)  echo 256 256 256;; 2)  echo 512 256 256;; 4)  echo 512 512 256;;
  8)  echo 512 512 512;; 16) echo 1024 512 512;; 32) echo 1024 1024 512;;
  *) return 1;; esac; }

export RCELLS=16 PHI=0.50 MGLEVELS=7 NSTEPS=25 WARMUP=5 MARCH_TOL=1e-5 MARCH_MAX=400
MAXN=$(( SLURM_NNODES * 4 ))

pack_one () {  # gnx gny gnz seed -> echoes npz path (packs on one GPU if missing)
  local gnx=$1 gny=$2 gnz=$3 seed=$4
  local npz="$PACKS/packing_${gnx}x${gny}x${gnz}_r${RCELLS}_phi${PHI}_s${seed}.npz"
  [ -f "$npz" ] || env GNX=$gnx GNY=$gny GNZ=$gnz SEED=$seed OUT="$npz" \
      srun --ntasks=1 --gpus-per-task=1 "$VENV/bin/python" "$EXDIR/../pack_bed.py" \
      >> "$RES/pack.log" 2>&1 || { echo "[FATAL] packing failed (see $RES/pack.log)"; return 1; }
  echo "$npz"
}

run_one () {  # N ibm out extra-env...
  local N=$1 ibm=$2 out=$3; shift 3
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  read -r gnx gny gnz <<< "$(grid_of $N)" || { echo "[FATAL] no grid for N=$N"; return 1; }
  local npz; npz=$(pack_one $gnx $gny $gnz $((100 + N))) || return 1
  echo "======= N=$N $ibm : ${gnx}x${gny}x${gnz} = $(( gnx * gny * gnz / 1000000 ))M  ($out) ======="
  env GNX=$gnx GNY=$gny GNZ=$gnz PACK="$npz" IBM=$ibm LABEL="snellius-h100" OUT="$RES/$out" "$@" \
    srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXDIR/../spheres_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[(perf|march|sdf)" "$RES/${out%.json}.log" \
    || { echo "  [FAILED N=$N $ibm] (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|out of memory|assert|FATAL" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

ARG="${1:-}"; TAG="${2:+_${2}}"
if [ -n "$ARG" ] && [ "$ARG" != levers ]; then
  [ "$ARG" -le "$MAXN" ] || { echo "FATAL: N=$ARG needs $(( (ARG+3)/4 )) nodes, allocated $SLURM_NNODES" >&2; exit 1; }
  run_one "$ARG" cutcell "weak_np${ARG}_cutcell${TAG}.json"
  run_one "$ARG" ghost   "weak_np${ARG}_ghost${TAG}.json"
else
  for N in 1 2 4 8 16 32; do
    [ "$N" -le "$MAXN" ] || continue
    run_one $N cutcell "weak_np${N}_cutcell${TAG}.json"
    run_one $N ghost   "weak_np${N}_ghost${TAG}.json"
  done
fi

# Levers at the allocated max: the smoothed (legacy) bottom quantifies the agglomerated bottom's
# at-scale iteration win on the IBM path; host-staged isolates the GPU-aware MPI gain.
if [ "$ARG" = levers ]; then
  run_one $MAXN cutcell "weak_np${MAXN}_cutcell_smoother${TAG}.json" env BOTTOM=smoother
  run_one $MAXN cutcell "weak_np${MAXN}_cutcell_hoststage${TAG}.json" env PECLET_CORE_GPU_AWARE_MPI=0
  run_one $MAXN ghost   "weak_np${MAXN}_ghost_smoother${TAG}.json"   env BOTTOM=smoother
fi

# Fat-block amortization ablation (suite docs/COMMUNICATION_SCALING.md §2.1): 512^3 cells/GPU
# at 32 GPUs (2048x2048x1024 = 4.3G cells; blocks are exactly 512^3 on the 4x4x2 split,
# ~134M cells/GPU, ~35-40GB of 94GB). Quantifies how
# much of the weak-efficiency gap is halo amortization before any code changes. Cut-cell only
# (the ghost march is unstable at large elongated rungs); the bed is packed on the CPU dem
# build (H100 packing-corruption workaround, see README).
#   sbatch --nodes=8 --time=01:30:00 spheres_weak_gpu.sh fat
if [ "$ARG" = fat ]; then
  [ "$MAXN" -ge 32 ] || { echo "FATAL: fat rung needs 8 nodes (32 GPUs)" >&2; exit 1; }
  out="weak_np32_cutcell_fat${TAG}.json"
  if [ -f "$RES/$out" ]; then echo "[skip] $out"; else
    npz="$PACKS/packing_2048x2048x1024_r${RCELLS}_phi${PHI}_s132.npz"
    [ -f "$npz" ] || env DEM_BUILD="$SUITE/dem/build_omp" \
        GNX=2048 GNY=2048 GNZ=1024 SEED=132 OUT="$npz" \
        OMP_NUM_THREADS=16 OMP_PROC_BIND=spread OMP_PLACES=threads \
        srun --ntasks=1 --cpus-per-task=16 "$VENV/bin/python" "$EXDIR/../pack_bed.py" \
        >> "$RES/pack.log" 2>&1 || { echo "[FATAL] fat packing failed (see $RES/pack.log)"; exit 1; }
    echo "======= FAT: 32 GPUs x 512^3 cells/GPU : 2048x2048x1024 = 4295M  ($out) ======="
    env GNX=2048 GNY=2048 GNZ=1024 PACK="$npz" IBM=cutcell MGLEVELS=8 \
        LABEL="snellius-h100-fat" OUT="$RES/$out" \
      srun --mpi=pmix --ntasks=32 --gpus-per-task=1 --gpu-bind=per_task:1 \
      "$VENV/bin/python" "$EXDIR/../spheres_bench.py" > "$RES/${out%.json}.log" 2>&1 \
      && grep -E "^\[(perf|march|sdf)" "$RES/${out%.json}.log" \
      || { echo "  [FAILED fat] (full log: $RES/${out%.json}.log):"
           grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
           grep -m3 -iE "Error:|out of memory|FATAL" "$RES/${out%.json}.log" | sed 's/^/    /'; }
  fi
fi
echo "done -> $RES"
