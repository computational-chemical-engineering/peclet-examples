#!/usr/bin/env bash
# Reference-code weak scaling on the workstation: CaNS and OpenFOAM on the same tiled-TGV case
# as bench_workstation.sh part B (128^3 = 2.1M cells per rank, pure MPI, x grows).
# Usage: ./bench_references.sh [cans|openfoam|all]     (default all)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
RES="$HERE/results/workstation"
mkdir -p "$RES"
part="${1:-all}"

if [ "$part" = cans ] || [ "$part" = all ]; then
  echo "== CaNS weak scaling, 2.1M cells/rank =="
  for np in 1 2 4 8 16 24; do
    out="$RES/cans_weak_np${np}.json"
    [ -f "$out" ] && { echo "[skip] $out"; continue; }
    NP=$np NX=$((128 * np)) NY=128 NZ=128 NSTEPS=25 TILE=64 \
      LABEL="workstation-cans" OUT="$out" "$HERE/run_cans.sh" || echo "[FAIL] $out"
  done
fi

if [ "$part" = openfoam ] || [ "$part" = all ]; then
  echo "== OpenFOAM weak scaling, 2.1M cells/rank =="
  for np in 1 2 4 8 16 24; do
    out="$RES/of_weak_np${np}.json"
    [ -f "$out" ] && { echo "[skip] $out"; continue; }
    NP=$np NX=$((128 * np)) NY=128 NZ=128 NSTEPS=20 TILE=64 \
      LABEL="workstation-openfoam" OUT="$out" "$HERE/openfoam-tgv/run_openfoam.sh" || echo "[FAIL] $out"
  done
fi
echo "== done: $RES =="
