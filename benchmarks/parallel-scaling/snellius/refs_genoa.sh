#!/bin/bash
# ==========================================================================================
# Reference codes on Snellius genoa: CaNS + OpenFOAM weak scaling on the same tiled-TGV case
# as tgv_genoa.sh MODE=weak (188M cells/node, GNX grows with nodes).
#
# Mode is the SCRIPT ARGUMENT (SURF sbatch drops leading env vars):
#   One-time builds:       sbatch --nodes=1 refs_genoa.sh build            # CaNS
#                          sbatch --nodes=1 refs_genoa.sh incflo-build     # incflo (AMReX superbuild)
#                          sbatch --nodes=1 --time=03:00:00 refs_genoa.sh openfoam-build
#                              # ESI OpenFOAM v2412 from source (~1h at -j 96) — the SAME version
#                              # and case dialect as the workstation reference; Snellius' central
#                              # module is the Foundation fork (OpenFOAM/12), a different dialect.
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
echo "[refs] start $(date '+%T') host=$(hostname) mode='${1:-<none>}' submitdir=${SLURM_SUBMIT_DIR:-?}"
set -uo pipefail
set -x   # full trace: this script once failed EMPTY-output — never allow that again
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

if [ "$MODE" = openfoam-build ]; then
  cd "$REFDIR"
  for f in OpenFOAM-v2412 ThirdParty-v2412; do
    [ -f "$f.tgz" ] || wget -q "https://dl.openfoam.com/source/v2412/$f.tgz"
    [ -d "$f" ] || tar xzf "$f.tgz"
  done
  cd OpenFOAM-v2412
  # WM_LABEL_SIZE=64: 32-bit labels overflow (SIGABRT in polyMesh::setTopology) past ~2e8 cells —
  # the n>=2 weak grids exceed 1e9 faces. Explicit source args also suppress caller-arg forwarding.
  set +u; source etc/bashrc WM_LABEL_SIZE=64 || true; set -u
  [ -n "${WM_PROJECT_DIR:-}" ] || { echo "FATAL: OpenFOAM env did not source" >&2; exit 1; }
  ./Allwmake -j 96 -s -q -l
  command -v icoFoam && echo "OpenFOAM v2412 built"
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
  # optional 2nd argument = explicit pencil grid "PxQ" (e.g. `refs_genoa.sh cans 2x192`):
  # fairness sweep for the FFT-transpose layout; output tagged with the dims.
  DIMS_ARG="${2:-}"
  if [ -n "$DIMS_ARG" ]; then
    DIMS="${DIMS_ARG/x/,}"; TAG="_d${DIMS_ARG}"
  else
    DIMS="0,0"; TAG=""
  fi
  OUT="$RES/cans_weak_n${N}${TAG}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  NP=$NP NX=$(( BASE_GNX * N )) NY=$GNY NZ=$GNZ NSTEPS=20 TILE=$TILE \
    LABEL="snellius-genoa-cans" OUT="$OUT" DIMS="$DIMS" \
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
  # source-built ESI v2412 (refs_genoa.sh openfoam-build) — same version + case dialect as the
  # workstation reference. Snellius' central module is the Foundation fork (different dialect).
  # NB stderr NOT discarded: this source once exited the job silently and the discarded stderr
  # hid the reason for days. And `set --` first: bash passes the CALLER's positional args to a
  # sourced script — foam's bashrc read our mode argument 'openfoam' as FOAM_SETTINGS, sourced
  # the etc/openfoam wrapper, and exit-1'd the whole job on its leftover options.
  # WM_LABEL_SIZE=64 must match the build (Int64 labels; Int32 SIGABRTs past ~2e8 cells).
  set +u; set --; source "$REFDIR/OpenFOAM-v2412/etc/bashrc" WM_LABEL_SIZE=64 || true; set -u
  command -v icoFoam >/dev/null || {
    echo "FATAL: icoFoam not on PATH — run 'sbatch --nodes=1 --time=03:00:00 refs_genoa.sh openfoam-build' first" >&2
    exit 1; }
  echo "[openfoam] using $(command -v icoFoam)"
  NP=$(( 192 * N ))
  OUT="$RES/of_weak_n${N}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  FOAM_NATIVE=1 NP=$NP NX=$(( BASE_GNX * N )) NY=$GNY NZ=$GNZ NSTEPS=10 TILE=$TILE \
    LABEL="snellius-genoa-openfoam" OUT="$OUT" \
    "$EXDIR/../openfoam-tgv/run_openfoam.sh"
fi
echo "done -> $RES"
