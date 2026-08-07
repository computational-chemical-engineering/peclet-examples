#!/bin/bash
# ==========================================================================================
# TGV CPU scaling on Snellius genoa (192 cores/node) — two modes in one script:
#
#   MODE=mix  (default, --nodes=1): ranks x threads sweep at fixed 768x640x384 = 188M
#             (~1M cells/core): 192x1, 96x2, 48x4, 24x8, 12x16
#   MODE=weak (--nodes=1..8): weak scaling at the chosen mix (default RPN=96 x THREADS=2),
#             188M cells/node fixed, GNX grows with node count
#
#   sbatch --nodes=1 tgv_genoa.sh
#   MODE=weak sbatch --nodes=4 tgv_genoa.sh
#   MODE=weak RPN=192 THREADS=1 sbatch --nodes=2 tgv_genoa.sh
# ==========================================================================================
#SBATCH --job-name=tgv-genoa
#SBATCH --partition=genoa
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=01:30:00
#SBATCH --output=tgv-genoa-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
module purge; module load 2024 gompi/2024a
module load Python/3.12.3-GCCcore-13.3.0 2>/dev/null || true

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/flow/build_omp_mpi}"        # OpenMP-backend + PECLET_FLOW_MPI build
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
RES="$EXDIR/results/snellius-genoa"; mkdir -p "$RES"
export TILE=64 GNY=640 GNZ=384 RE=100 ADV=0 OMP_PROC_BIND=spread OMP_PLACES=cores
BASE_GNX=768    # 768x640x384 = 188.7M / node (~1M cells/core at 192 c/node)

run_one () {  # ntasks rpn threads gnx out
  local nt=$1 rpn=$2 th=$3 gnx=$4 out=$5
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  echo "======= $out : ${gnx}x${GNY}x${GNZ}, $nt ranks x $th threads ======="
  env GNX=$gnx OMP_NUM_THREADS=$th LABEL="snellius-genoa" OUT="$RES/$out" \
    srun --mpi=pmix --ntasks=$nt --ntasks-per-node=$rpn --cpus-per-task=$th \
    "$VENV/bin/python" "$EXDIR/../tgv_bench.py" > "$RES/${out%.json}.log" 2>&1 \
    && grep -E "^\[result" "$RES/${out%.json}.log" \
    || { echo "  [FAILED $out] rank-0 error (full log: $RES/${out%.json}.log):"
         grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
         grep -m3 -iE "Error:|ModuleNotFound|ImportError|assert" \
           "$RES/${out%.json}.log" | sed 's/^/    /'; }
}

MODE="${MODE:-mix}"
if [ "$MODE" = mix ]; then
  export NSTEPS=15 WARMUP=5
  for cfg in "192 1" "96 2" "48 4" "24 8" "12 16"; do
    set -- $cfg
    run_one "$1" "$1" "$2" "$BASE_GNX" "mix_r$1_t$2.json"
  done
else
  export NSTEPS=15 WARMUP=5
  RPN="${RPN:-96}"; THREADS="${THREADS:-2}"
  N=$SLURM_NNODES
  run_one $(( RPN * N )) "$RPN" "$THREADS" $(( BASE_GNX * N )) "weak_n${N}_r${RPN}_t${THREADS}.json"
fi
echo "done -> $RES"
