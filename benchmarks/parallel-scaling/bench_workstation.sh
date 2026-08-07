#!/usr/bin/env bash
# Workstation scaling study for the parallel-scaling benchmark page.
# Machine: AMD Threadripper PRO 5965WX (24 cores), 503 GB RAM, RTX 5080 16 GB.
#
#   A. CPU hybrid-mix: fixed 192^3 (7.1M cells), ranks x threads = 24 cores every way
#   B. CPU weak scaling: 128^3 = 2.1M cells per rank, np = 1..24 (pure MPI, x grows)
#   C. GPU (single RTX 5080): grid sizes up to the 16 GB memory cap
#
# Usage:  ./bench_workstation.sh [A|B|C|all]     (default all)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SUITE="${SUITE:-$HERE/../../../suite}"
PY="$SUITE/flow/.venv/bin/python"
BUILD_CPU="$SUITE/flow/build_mpi_omp_ch"
BUILD_GPU="$SUITE/flow/build_cuda_mpi_ch"
MPIRUN="${MPIRUN:-/usr/bin/mpirun}"
RES="$HERE/results/workstation"
mkdir -p "$RES"
export OMP_PROC_BIND=spread OMP_PLACES=cores
export TILE=64 RE=100 CFL=0.2 ADV=0 PRESSURE="${PRESSURE:-pcg}"

part="${1:-all}"

run_cpu () { # np threads gnx gny gnz nsteps warmup out
  local np=$1 t=$2 gnx=$3 gny=$4 gnz=$5 nsteps=$6 warmup=$7 out=$8
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  echo "[run] np=$np threads=$t  ${gnx}x${gny}x${gnz}"
  PYTHONPATH="$BUILD_CPU" OMP_NUM_THREADS=$t \
  GNX=$gnx GNY=$gny GNZ=$gnz NSTEPS=$nsteps WARMUP=$warmup \
  LABEL="workstation-5965wx" OUT="$RES/$out" \
  "$MPIRUN" -np $np --map-by slot:pe=$t --bind-to core "$PY" "$HERE/tgv_bench.py" \
    2>&1 | grep -E "^\[(result|phases|out)\]" || echo "[FAIL] $out"
}

if [ "$part" = A ] || [ "$part" = all ]; then
  echo "== A: hybrid MPI x OpenMP mix, 192^3 fixed =="
  run_cpu  1  1 192 192 192  6 2 mix_r1_t1.json     # serial baseline (slow -> few steps)
  run_cpu 24  1 192 192 192 25 5 mix_r24_t1.json
  run_cpu 12  2 192 192 192 25 5 mix_r12_t2.json
  run_cpu  6  4 192 192 192 25 5 mix_r6_t4.json
  run_cpu  4  6 192 192 192 25 5 mix_r4_t6.json
  run_cpu  2 12 192 192 192 25 5 mix_r2_t12.json
  run_cpu  1 24 192 192 192 25 5 mix_r1_t24.json
fi

if [ "$part" = B ] || [ "$part" = all ]; then
  echo "== B: CPU weak scaling, 128^3 = 2.1M cells/rank, pure MPI =="
  for np in 1 2 4 8 16 24; do
    run_cpu $np 1 $((128 * np)) 128 128 25 5 weak_np${np}.json
  done
fi

if [ "$part" = C ] || [ "$part" = all ]; then
  echo "== C: single GPU (RTX 5080), size ladder =="
  for n in 128 160 192 208; do   # 208^3 = 9.0M cells ~ the 16 GB cap; 256^3 OOMs
    out=gpu_${n}.json
    [ -f "$RES/$out" ] && { echo "[skip] $out"; continue; }
    echo "[run] GPU ${n}^3"
    PYTHONPATH="$BUILD_GPU" \
    GNX=$n GNY=$n GNZ=$n NSTEPS=50 WARMUP=10 \
    LABEL="workstation-rtx5080" OUT="$RES/$out" \
    "$MPIRUN" -np 1 "$PY" "$HERE/tgv_bench.py" \
      2>&1 | grep -E "^\[(result|phases|out)\]" || echo "[FAIL] $out"
  done
fi
echo "== done: $RES =="
