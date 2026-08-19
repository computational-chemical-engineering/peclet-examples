#!/bin/bash
# Where does the collocated-vs-staggered difference live, at the rungs where the permeability
# ceiling actually appears? The workstation could only reach R=8/12, which are PRE-crossover
# (the gap crosses zero near R=16) and therefore say nothing about the plateau.
# Argument 1 = N (256 -> R=16, 384 -> R=24, 512 -> R=32).
#SBATCH --job-name=wallband
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --time=06:00:00
#SBATCH --output=wallband-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
SUITE=/projects/0/prjs1022/peclet/suite
RES="$EXDIR/results/snellius-h100"; mkdir -p "$RES"
export BED="$EXDIR/../results/packings/packing_256x256x256_r16_phi0.50_s100.npz"
export SDFLOW_BUILD=build_cuda_mpi
srun --ntasks=1 --gpus-per-task=1 "$SUITE/flow/.venv/bin/python" \
  "$SUITE/flow/tests/study/zh_wallband_diff.py" "$1" > "$RES/wallband_N$1.log" 2>&1
grep -vE "^\[0x|Kokkos|backtrace" "$RES/wallband_N$1.log" | tail -8
