#!/bin/bash
# ==========================================================================================
# The momentum-solver campaign: the SAME fixed-384^3 CPU strong-scaling ladder as the 1.0.0
# deposit, but with the momentum solver PINNED across every rung instead of left to the auto
# rule that switches it below 65536 cells/rank (which only the 1536-core rung crosses).
#
#   ./snellius/submit_momentum.sh off      # red-black Gauss-Seidel at every rank count
#   ./snellius/submit_momentum.sh on       # velocity V-cycle at every rank count (3 levels, 40)
#   ./snellius/submit_momentum.sh probe    # just the two rungs that bracket the auto threshold
#
# Rungs match the deposit exactly (24 48 96 192 384 768 1536) so the two ladders and the
# published `auto` one are directly comparable. Billing: genoa, ~1.5 node-hours per ladder.
#
# Extra settings go through --export, NEVER as a leading `VAR=x sbatch`: SURF's sbatch drops
# those SILENTLY (suite docs/SNELLIUS.md).
# ==========================================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
BENCH="$PWD"
export BENCH
mkdir -p "$BENCH/logs" "$BENCH/results/snellius-genoa"

cpu() {  # cpu <nranks> <tag> <extra env assignments...>
  local n=$1 tag=$2; shift 2
  local nodes=$(( (n + 191) / 192 ))
  local e="ALL,BENCH=$BENCH"
  local kv; for kv in "$@"; do e="$e,$kv"; done
  echo "-- cpu strong/bed n=$n nodes=$nodes tag=$tag  $*"
  sbatch -D "$BENCH/logs" --export="$e" --nodes=$nodes --ntasks=$n \
      "$BENCH/snellius/run_cpu.sh" strong bed "$n" "$tag" | tail -1
}

MODE="${1:?usage: submit_momentum.sh <off|on|probe>}"
case "$MODE" in
  off)   for n in 24 48 96 192 384 768 1536; do cpu $n vmgoff VMG=off; done ;;
  on)    for n in 24 48 96 192 384 768 1536; do cpu $n vmgon  VMG=on;  done ;;
  probe) cpu 768 vmgon VMG=on; cpu 1536 vmgoff VMG=off ;;
  *) echo "unknown mode '$MODE'" >&2; exit 1 ;;
esac
squeue -u "$USER" --format="%.10i %.9P %.20j %.8T %.7M %R"
