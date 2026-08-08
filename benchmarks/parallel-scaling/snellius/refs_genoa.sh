#!/bin/bash
# ==========================================================================================
# Reference codes on Snellius genoa: CaNS + OpenFOAM weak scaling on the same tiled-TGV case
# as tgv_genoa.sh MODE=weak (188M cells/node, GNX grows with nodes).
#
# Mode is the SCRIPT ARGUMENT (SURF sbatch drops leading env vars):
#   One-time builds:       sbatch --nodes=1 refs_genoa.sh build          # CaNS
#                          sbatch --nodes=1 refs_genoa.sh incflo-build   # incflo (AMReX superbuild)
#   Weak points:           sbatch --nodes=2 refs_genoa.sh cans
#                          sbatch --nodes=2 refs_genoa.sh openfoam
#                          sbatch --nodes=2 refs_genoa.sh incflo
#
# OpenFOAM caveat: blockMesh+decomposePar are SERIAL — mesh generation for >2 nodes' worth of
# cells (>380M) takes long + lots of RAM on one core. OpenFOAM runs use RPN=192 (pure MPI, its
# only mode); CaNS likewise pure MPI.
# ==========================================================================================
#SBATCH --job-name=tgv-refs
#SBATCH --partition=genoa
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=tgv-refs-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
RES="$EXDIR/results/snellius-genoa"; mkdir -p "$RES"
REFDIR="${REFDIR:-/projects/0/prjs1022/peclet/scaling-refs}"; mkdir -p "$REFDIR"
export TILE=64 GNY=640 GNZ=384
BASE_GNX=768
N=${SLURM_NNODES:-1}

module purge; module load 2024 foss/2024a          # GCC + OpenMPI + FFTW (CaNS needs FFTW)

MODE="${1:-${CODE:-cans}}"   # argument beats env (env vars can be dropped by SURF sbatch)
if [ "$MODE" = build ] || [ "${BUILD_CANS:-0}" = 1 ]; then
  cd "$REFDIR"
  [ -d CaNS ] || git clone https://github.com/CaNS-World/CaNS.git
  cd CaNS
  git submodule update --init dependencies/2decomp-fft
  cp -n configs/defaults/build-default.conf build.conf
  make libs && make -j 16          # libs MUST be serial (Fortran module race)
  ls -la run/cans && echo "CaNS built"
  exit 0
fi

if [ "$MODE" = incflo-build ]; then
  module load CMake 2>/dev/null || true
  cd "$REFDIR"
  [ -d incflo ] || git clone --depth 1 https://github.com/AMReX-Fluids/incflo.git
  [ -d amrex ] || git clone --depth 1 https://github.com/AMReX-Codes/amrex.git
  [ -d AMReX-Hydro ] || git clone --depth 1 https://github.com/AMReX-Fluids/AMReX-Hydro.git
  cd incflo
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DAMREX_HOME=../amrex \
    -DAMREX_HYDRO_HOME=../AMReX-Hydro -DINCFLO_DIM=3 -DINCFLO_MPI=ON -DINCFLO_OMP=OFF \
    -DCMAKE_CXX_FLAGS=-march=native
  cmake --build build -j 32
  ls -la build/incflo.ex && echo "incflo built"
  exit 0
fi

CODE="$MODE"
if [ "$CODE" = cans ]; then
  NP=$(( 192 * N ))
  OUT="$RES/cans_weak_n${N}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  NP=$NP NX=$(( BASE_GNX * N )) NY=$GNY NZ=$GNZ NSTEPS=20 TILE=$TILE \
    LABEL="snellius-genoa-cans" OUT="$OUT" \
    CANS="$REFDIR/CaNS/run/cans" MPIRUN="srun" NPFLAG="-n" MPIFLAGS="--mpi=pmix" \
    "$EXDIR/../run_cans.sh" || echo "[FAILED] $OUT"
elif [ "$CODE" = incflo ]; then
  NP=$(( 192 * N ))
  OUT="$RES/incflo_weak_n${N}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  NP=$NP NX=$(( BASE_GNX * N )) NY=$GNY NZ=$GNZ NSTEPS=15 TILE=$TILE \
    LABEL="snellius-genoa-incflo" OUT="$OUT" \
    INCFLO="$REFDIR/incflo/build/incflo.ex" MPIRUN="srun" NPFLAG="-n" MPIFLAGS="--mpi=pmix" \
    "$EXDIR/../run_incflo.sh" || echo "[FAILED] $OUT"
elif [ "$CODE" = openfoam ]; then
  # OpenFOAM modules may live under a different toolchain year than the loaded 2024 stack:
  # enumerate across years, load the newest v-series, fail LOUDLY with the available list.
  OFMOD="$(module -r -t avail '^OpenFOAM' 2>&1 | grep -E '^OpenFOAM/v[0-9]' | sort -V | tail -1)"
  if [ -z "$OFMOD" ]; then
    module load 2023 2>/dev/null || true
    OFMOD="$(module -r -t avail '^OpenFOAM' 2>&1 | grep -E '^OpenFOAM/v[0-9]' | sort -V | tail -1)"
  fi
  [ -n "$OFMOD" ] || { echo "FATAL: no OpenFOAM module found; module avail says:" >&2
                       module -r avail '^OpenFOAM' 2>&1 | tail -20 >&2; exit 1; }
  echo "[openfoam] using module $OFMOD"
  module load "$OFMOD" || { echo "FATAL: module load $OFMOD failed" >&2; exit 1; }
  source "${FOAM_BASH:-$WM_PROJECT_DIR/etc/bashrc}" 2>/dev/null || true
  NP=$(( 192 * N ))
  OUT="$RES/of_weak_n${N}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  FOAM_NATIVE=1 NP=$NP NX=$(( BASE_GNX * N )) NY=$GNY NZ=$GNZ NSTEPS=10 TILE=$TILE \
    LABEL="snellius-genoa-openfoam" OUT="$OUT" \
    "$EXDIR/../openfoam-tgv/run_openfoam.sh"
fi
echo "done -> $RES"
