#!/bin/bash
# ==========================================================================================
# Reference codes on Snellius gpu_h100: incflo (AMReX CUDA) and CaNS (OpenACC + cuDecomp)
# on the SAME weak-scaling grids as peclet's GPU study (47.2M cells/GPU: 384N x 384 x 320).
#
# Mode is the SCRIPT ARGUMENT (SURF sbatch drops leading env vars):
#   One-time builds:  sbatch --nodes=1 tgv_gpu_refs.sh incflo-build
#                     sbatch --nodes=1 tgv_gpu_refs.sh cans-build
#   Weak points (N = GPUs = allocated nodes x 4):
#                     sbatch --nodes=1 tgv_gpu_refs.sh incflo 4
#                     sbatch --nodes=2 tgv_gpu_refs.sh cans 8      etc.
# ==========================================================================================
#SBATCH --job-name=tgv-gpuref
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=00:45:00
#SBATCH --output=tgv-gpuref-%j.out
#SBATCH --account=tes24005
echo "[gpuref] start $(date '+%T') host=$(hostname) mode='${1:-<none>}' n='${2:-}'"
set -uo pipefail
set -x
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
RES="$EXDIR/results/snellius-h100"; mkdir -p "$RES"
REFDIR="${REFDIR:-/projects/0/prjs1022/peclet/scaling-refs}"; mkdir -p "$REFDIR"
export TILE=64
MODE="${1:-}"; NGPU="${2:-4}"

# Put an MPI for nvfortran on PATH (the NVHPC module alone ships no mpifort). Route 1: a
# site OpenMPI built against NVHPC; route 2: NVHPC's bundled comm_libs MPI. Sets CANS_MPIRUN
# for the run mode (bundled MPI is not Slurm/pmix-integrated -> launch with its own mpirun).
nvhpc_mpi () {
  CANS_MPIRUN=srun; CANS_NPFLAG="-n"
  CANS_MPIFLAGS="--mpi=pmix --gpus-per-task=1 --gpu-bind=per_task:1"
  if ! command -v mpifort >/dev/null; then
    OMPIMOD="$(module -r -t avail 'OpenMPI.*NVHPC' 2>&1 | grep -iE '^OpenMPI' | sort -V | tail -1)"
    [ -n "$OMPIMOD" ] && module load "$OMPIMOD" && echo "[nvhpc_mpi] loaded $OMPIMOD"
  fi
  if ! command -v mpifort >/dev/null && [ -n "${EBROOTNVHPC:-}" ]; then
    for d in "$EBROOTNVHPC"/Linux_x86_64/*/comm_libs/mpi; do
      [ -x "$d/bin/mpifort" ] || continue
      export PATH="$d/bin:$PATH" LD_LIBRARY_PATH="$d/lib:${LD_LIBRARY_PATH:-}"
      CANS_MPIRUN="$d/bin/mpirun"; CANS_NPFLAG="-np"; CANS_MPIFLAGS=" "
      echo "[nvhpc_mpi] using NVHPC bundled MPI: $d (launcher: its mpirun, GPU binding by local rank)"
    done
  fi
  command -v mpifort >/dev/null || {
    echo "FATAL: no mpifort for nvfortran; OpenMPI modules seen:" >&2
    module -r avail 'OpenMPI' 2>&1 | tail -15 >&2; exit 1; }
}

if [ "$MODE" = incflo-build ]; then
  # the peclet-validated GPU MPI stack (gompi/2024a + CUDA 12.6 + UCX-CUDA + pml=ucx): plain
  # foss UCX has no CUDA support -> CMA aborts on CUDA-registered buffers in FillBoundary
  set --; source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
  module load CMake 2>/dev/null || true
  cd "$REFDIR"
  [ -d incflo ] || git clone --depth 1 https://github.com/AMReX-Fluids/incflo.git
  [ -d amrex ] || git clone --depth 1 https://github.com/AMReX-Codes/amrex.git
  [ -d AMReX-Hydro ] || git clone --depth 1 https://github.com/AMReX-Fluids/AMReX-Hydro.git
  # AMReX arch plumbing silently drops SM>=10.0 and can fall back to sm_86 via CMake's stale
  # FindCUDA table; the bypass patch is harmless for sm_90 but applied for robustness (idempotent).
  U=amrex/Tools/CMake/AMReXUtils.cmake
  grep -q "LOCAL PATCH" $U || python3 - "$U" <<'EOF'
import re, sys
p = sys.argv[1]; s = open(p).read()
patch = '''   set(_archs ${${_cuda_archs}})

   if (_archs MATCHES "^[0-9]+(;[0-9]+)*$")  # LOCAL PATCH: numeric archs bypass the stale table
      set(AMREX_CUDA_ARCHS ${_archs} CACHE INTERNAL "CUDA archs AMReX is built for")
      return()
   endif ()
'''
s = s.replace('''function (set_cuda_architectures _cuda_archs)

   set(_archs ${${_cuda_archs}})
''', 'function (set_cuda_architectures _cuda_archs)\n\n' + patch, 1)
open(p, 'w').write(s)
EOF
  cd incflo
  cmake -S . -B build_gpu -DCMAKE_BUILD_TYPE=Release -DAMREX_HOME=../amrex \
    -DAMREX_HYDRO_HOME=../AMReX-Hydro -DINCFLO_DIM=3 -DINCFLO_MPI=ON -DINCFLO_OMP=OFF \
    -DINCFLO_CUDA=ON -DAMReX_CUDA_ARCH=90
  cmake --build build_gpu -j 32
  ls -la build_gpu/incflo.ex && echo "incflo GPU built"
  exit 0
fi

if [ "$MODE" = cans-build ]; then
  # CaNS GPU = OpenACC via nvfortran + cuDecomp — in a SEPARATE CaNS-gpu checkout (building
  # GPU=1 in the CPU checkout destroys the genoa CPU binary and poisons its build.conf; the
  # workstation recipe uses the same split). Loud failure with the module list if no NVHPC.
  module purge; module load 2024 2>/dev/null || true
  NVMOD="$(module -r -t avail '^NVHPC' 2>&1 | grep -E '^NVHPC' | sort -V | tail -1)"
  [ -n "$NVMOD" ] || { echo "FATAL: no NVHPC module:"; module -r avail 'NVHPC|nvhpc' 2>&1 | tail; exit 1; }
  module load "$NVMOD"
  nvhpc_mpi   # Snellius' NVHPC module ships no mpifort on PATH — see helper at top
  cd "$REFDIR"
  [ -d CaNS-gpu ] || git clone --depth 1 https://github.com/CaNS-World/CaNS.git CaNS-gpu
  cd CaNS-gpu
  git submodule update --init dependencies/2decomp-fft dependencies/cuDecomp
  cp -f configs/defaults/build-default.conf build.conf
  sed -i 's/^FCOMP=.*/FCOMP=NVIDIA/; s/^GPU=.*/GPU=1/' build.conf
  grep -E "FCOMP|GPU" build.conf
  make allclean || true
  make libs && make -j 16
  ls -la run/cans || { echo "FATAL: no GPU binary produced" >&2; exit 1; }
  # a correct GPU binary links cuFFT, not FFTW — fail here rather than at 8 GPUs' runtime
  ldd run/cans | grep -q fftw3 && { echo "FATAL: binary links FFTW -> this is a CPU build" >&2; exit 1; }
  echo "CaNS GPU built"
  exit 0
fi

# ---- run modes: incflo | cans, weak grid 384N x 384 x 320 -------------------------------------
GNX=$(( 384 * NGPU )); GNY=384; GNZ=320
case "$MODE" in
incflo)
  # same validated GPU MPI env as the peclet runs (UCX-CUDA); device-direct AMReX communication.
  # UCX_TLS=^cma: the CMA transport's process_vm_readv cannot touch CUDA-registered memory
  # (measured: SIGABRT 'Bad address' in FillBoundary) — drop it, UCX falls back to sm/sysv.
  set --; source "$EXDIR/../../../examples/wall-bounded-turbulence/snellius_env.sh"
  export UCX_TLS='^cma'
  OUT="$RES/incflo_gpu_np${NGPU}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  NP=$NGPU NX=$GNX NY=$GNY NZ=$GNZ NSTEPS=30 TILE=$TILE MAXGRID=384 \
    EXTRA="amrex.use_gpu_aware_mpi = 1" \
    LABEL="snellius-h100-incflo" OUT="$OUT" \
    INCFLO="$REFDIR/incflo/build_gpu/incflo.ex" \
    MPIRUN="srun" NPFLAG="-n" MPIFLAGS="--mpi=pmix --gpus-per-task=1 --gpu-bind=per_task:1" \
    "$EXDIR/../run_incflo.sh" || echo "[FAILED] $OUT"
  ;;
cans)
  module purge; module load 2024 2>/dev/null || true
  NVMOD="$(module -r -t avail '^NVHPC' 2>&1 | grep -E '^NVHPC' | sort -V | tail -1)"
  module load "$NVMOD"
  nvhpc_mpi   # same MPI the binary was built with; sets CANS_MPIRUN/NPFLAG/MPIFLAGS
  export UCX_TLS='^cma'   # same CMA-vs-CUDA-memory hazard as incflo — preempt it
  export LD_LIBRARY_PATH="$REFDIR/CaNS-gpu/dependencies/cuDecomp/build/lib:${LD_LIBRARY_PATH:-}"
  ldd "$REFDIR/CaNS-gpu/run/cans" | grep -q fftw3 && {
    echo "FATAL: CaNS-gpu/run/cans links FFTW (CPU build) — rerun 'tgv_gpu_refs.sh cans-build'" >&2
    exit 1; }
  OUT="$RES/cans_gpu_np${NGPU}.json"
  [ -f "$OUT" ] && { echo "[skip] $OUT"; exit 0; }
  NP=$NGPU NX=$GNX NY=$GNY NZ=$GNZ NSTEPS=30 TILE=$TILE \
    LABEL="snellius-h100-cans" OUT="$OUT" \
    CANS="$REFDIR/CaNS-gpu/run/cans" \
    MPIRUN="$CANS_MPIRUN" NPFLAG="$CANS_NPFLAG" MPIFLAGS="$CANS_MPIFLAGS" \
    "$EXDIR/../run_cans.sh" || echo "[FAILED] $OUT"
  ;;
*) echo "FATAL: unknown mode '$MODE' (incflo-build|cans-build|incflo|cans)"; exit 1 ;;
esac
echo "done -> $RES"
