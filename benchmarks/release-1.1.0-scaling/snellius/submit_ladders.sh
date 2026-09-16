#!/bin/bash
# ==========================================================================================
# Queue the ladders of the peclet 1.1.0 scaling deposit. Run from the campaign directory on
# the Snellius login node:
#
#   ./snellius/submit_ladders.sh pilot        # 1 GPU + 4 GPU + 192 cores: the go/no-go rungs
#   ./snellius/submit_ladders.sh weak         # W: 1..32 GPUs, 384^3/GPU  (the headline)
#   ./snellius/submit_ladders.sh strong-gpu   # T: 1..32 GPUs, fixed 384^3
#   ./snellius/submit_ladders.sh strong-cpu   # S: 24..1536 genoa cores, fixed 384^3
#   ./snellius/submit_ladders.sh tgv          # N: the geometry-free control, both machines
#   ./snellius/submit_ladders.sh march        # permeability at rungs 1 / 8 / 32 GPUs
#   ./snellius/submit_ladders.sh spread       # repeats of the top rungs (allocation spread)
#   ./snellius/submit_ladders.sh levels       # LEVELS=4 sensitivity (the shipped MG default)
#
# EVERY rung names its own --nodes/--gpus-per-node: billing is per ALLOCATED GPU, so a 1-GPU
# rung submitted with the script's 4-GPU header would cost four times what it uses.
# ==========================================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
BENCH="$PWD"
export BENCH

# Extra settings go through --export, NEVER as a leading `VAR=x sbatch`: SURF's sbatch drops
# those SILENTLY (bitten twice; see suite docs/SNELLIUS.md). BENCH is exported for the same reason
# it is passed here -- a batch script cannot find its own directory from the Slurm spool.
exports() {  # exports <extra assignments...> -> "ALL,BENCH=...,A=1,B=2"
  local e="ALL,BENCH=$BENCH"
  local kv
  for kv in "$@"; do e="$e,$kv"; done
  echo "$e"
}

gpu() {  # gpu <ngpus> <mode> <case> [tag] [extra env assignments...]
  local n=$1 mode=$2 case=$3 tag=${4:-}
  shift 3; if [ $# -gt 0 ]; then shift; fi   # set -e would abort on a bare "test && shift"
  local nodes gpn
  if [ "$n" -le 4 ]; then nodes=1; gpn=$n; else nodes=$(( n / 4 )); gpn=4; fi
  echo "-- gpu $mode/$case n=$n  nodes=$nodes gpus-per-node=$gpn ${*:-}"
  # shellcheck disable=SC2086
  sbatch -D "$BENCH/logs" --export="$(exports "$@")" --nodes=$nodes --gpus-per-node=$gpn \
      --ntasks-per-node=$gpn "$BENCH/snellius/run_gpu.sh" "$mode" "$case" "$n" $tag | tail -1
}

cpu() {  # cpu <nranks> <mode> <case> [tag] [extra env assignments...]
  local n=$1 mode=$2 case=$3 tag=${4:-}
  shift 3; if [ $# -gt 0 ]; then shift; fi   # set -e would abort on a bare "test && shift"
  local nodes=$(( (n + 191) / 192 ))
  echo "-- cpu $mode/$case n=$n  nodes=$nodes ${*:-}"
  # shellcheck disable=SC2086
  sbatch -D "$BENCH/logs" --export="$(exports "$@")" --nodes=$nodes --ntasks=$n \
      "$BENCH/snellius/run_cpu.sh" "$mode" "$case" "$n" $tag | tail -1
}

mkdir -p "$BENCH/logs"
case "${1:?usage: submit_ladders.sh <pilot|weak|strong-gpu|strong-cpu|tgv|march|spread|levels>}" in
  pilot)
    gpu 1 strong bed pilot
    gpu 4 weak   bed pilot
    cpu 192 strong bed pilot
    ;;
  weak)        for n in 1 2 4 8 16 32; do gpu $n weak bed; done ;;
  strong-gpu)  for n in 1 2 4 8 16 32; do gpu $n strong bed; done ;;
  strong-cpu)  for n in 24 48 96 192 384 768 1536; do cpu $n strong bed; done ;;
  tgv)
    for n in 1 4 16 32; do gpu $n weak tgv; done
    for n in 192 768 1536; do cpu $n strong tgv; done
    ;;
  march)       for n in 1 8 32; do gpu $n weak bed march MARCH_TOL=1e-5; done ;;
  spread)
    for r in r2 r3; do gpu 32 weak bed "$r"; cpu 1536 strong bed "$r"; done
    ;;
  levels)      gpu 8 weak bed levels4 LEVELS=4 ;;
  *) echo "unknown ladder '$1'" >&2; exit 1 ;;
esac
squeue -u "$USER" --format="%.10i %.9P %.20j %.8T %.7M %R"
