#!/bin/bash
# ==========================================================================================
# Channel-DNS weak scaling on Snellius gpu_h100 — 46.4M cells/GPU fixed.
#
# The per-GPU block is IDENTICAL at every point: GNY=240, GNZ=503 (the production Delta+=1.5
# cross-section; y is the wall-normal direction and must NEVER be split) and GNX = 384*N, so the
# ORB carves x into N blocks of exactly 384x240x503 = 46.4M cells. 384 is chosen over the
# production 377 purely for divisibility: every rank then owns a byte-identical block at every N,
# which is what a weak-scaling curve is supposed to compare. N=4 (1536x240x503 = 185M) is the
# production DNS box to within 2 %.
#
# Argument = the GPU count to measure (queue-parallel safe: each job touches only its own point),
# or 'levers' for the ablation at the allocated max. Argument, not env var — SURF sbatch drops
# leading env vars.
#   sbatch --nodes=1 chan_weak_gpu.sh 1
#   sbatch --nodes=1 chan_weak_gpu.sh 2
#   sbatch --nodes=1 chan_weak_gpu.sh 4
#   sbatch --nodes=2 chan_weak_gpu.sh 8
#   sbatch --nodes=4 chan_weak_gpu.sh 16
#   sbatch --nodes=8 chan_weak_gpu.sh 32
#   sbatch --nodes=8 chan_weak_gpu.sh refine      # THE HEADLINE LADDER (see `refine` below)
#   sbatch --nodes=2 chan_weak_gpu.sh levers      # CPG / mean-scope / MG depth / halo, at N=8
#   sbatch --nodes=2 chan_weak_gpu.sh strong      # OPTIONAL: fixed 46M box on 1,2,4,8 GPUs
#   sbatch --nodes=2 chan_weak_gpu.sh probe       # why the pressure solve hit its iteration cap
#
# Second argument = result TAG appended to every JSON (`chan_weak_gpu.sh 8 r2`). run_one SKIPS a
# JSON that already exists, so a re-measurement (solver change, repeat draw) NEEDS a new tag —
# otherwise the stale file is silently reported as the new number.
# ==========================================================================================
#SBATCH --job-name=chan-weak
#SBATCH --partition=gpu_h100
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=16
#SBATCH --time=00:40:00
#SBATCH --output=chan-weak-%j.out
#SBATCH --account=tes24005
set -uo pipefail
EXDIR="${SLURM_SUBMIT_DIR:-$PWD}"
EXAMPLE="$EXDIR/../../../examples/wall-bounded-turbulence"
source "$EXAMPLE/snellius_env.sh"

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"; BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"
VENV="${VENV:-$SUITE/flow/.venv}"; export PYTHONPATH="$BUILD:${PYTHONPATH:-}"
export PECLET_BIND_GPU=0 PECLET_CORE_GPU_AWARE_MPI="${GPU_AWARE:-1}"
RES="$EXDIR/../results/snellius-h100"; mkdir -p "$RES"

# Production channel physics: Re_tau=180, isotropic unit grid, SOU advection, CFR forcing (holds the
# bulk velocity — its own global Allreduce per step, outside the pressure solve; the `cpg` lever
# quantifies it). 100 warmup + 40 measured steps; DIAG=100 keeps the live diagnostic (and its
# gather) OUT of the measured window while still printing one sanity line per run.
export GNY=240 GNZ=503 DT=0.02 ADV=0 CFR=15.68 RE_TAU=180 NOISE=1.0 SEED=1234
export WARMUP=100 NSTEPS=140 DIAG=100 STATSTART=1000000000 CKPT=0 HB=20
BASE_GNX=384
MAXN=$(( SLURM_NNODES * 4 ))

FIXED_GNX=0    # strong-scaling mode sets this: same box on every rank count

run_one () {  # N out extra-env...
  local N=$1 out=$2; shift 2
  [ -f "$RES/$out" ] && { echo "[skip] $out"; return; }
  local gnx=$(( FIXED_GNX > 0 ? FIXED_GNX : BASE_GNX * N ))
  echo "======= N=$N : ${gnx}x${GNY}x${GNZ} = $(( gnx * GNY * GNZ / 1000000 ))M cells  ($out) ======="
  env GNX=$gnx LABEL="snellius-h100" BENCH_OUT="$RES/$out" \
      OUT="${TMPDIR:-/tmp}/chan_${out%.json}" "$@" \
    srun --mpi=pmix --ntasks=$N --gpus-per-task=1 --gpu-bind=per_task:1 \
    "$VENV/bin/python" "$EXAMPLE/channel_dns_mpi.py" > "$RES/${out%.json}.log" 2>&1
  # NEVER trust the exit status: the JSON is the only success criterion.
  if [ -f "$RES/$out" ]; then
    grep -E "^\[(timing|phases)" "$RES/${out%.json}.log"
  else
    echo "  [FAILED N=$N] no JSON (full log: $RES/${out%.json}.log):"
    grep -m1 -A6 "Traceback" "$RES/${out%.json}.log" | sed 's/^/    /'
    grep -m3 -iE "FATAL|Error:|ModuleNotFound|ImportError|out of memory|assert" \
      "$RES/${out%.json}.log" | sed 's/^/    /'
  fi
}

ARG="${1:-}"; TAG="${2:+_${2}}"

# ===== `refine`: the weak ladder a DNS user actually climbs ======================================
# The production job script (examples/wall-bounded-turbulence/snellius_gpu.slurm) scales this DNS by
# REFINING a fixed physical box rather than lengthening it: more GPUs buy a finer DNS of the same
# channel. This ladder is that, at ~46 Mcells/GPU.
#
# GRID DIMENSIONS ARE CHOSEN FOR THEIR FACTORS OF TWO, and that is not cosmetic. The pressure
# multigrid coarsens each axis independently while the axis is EVEN (mac_cutcell_mg.hpp: an axis
# halves while `d % 2 == 0 && d / 2 >= 2`), so a dimension's usable MG depth is the number of times
# it can be halved -- nothing to do with how large it is. An ODD dimension never coarsens even once.
# Measured on one H100-class GPU, 384x128xGNZ, everything else identical:
#
#     GNZ = 256 (8 halvings)   5.0 pressure iters/step   120 ms
#     GNZ = 250 (1 halving)    9.8                       195 ms
#     GNZ = 255 (0 halvings)  16.2                       329 ms     <- 3.2x, from ONE odd number
#
# The production preset derives its grid as GNX = round(2pi*GNY), GNZ = round(2pi/3*GNY), which for
# GNY=240 gives 1508 x 240 x 503: x halves twice, y four times, z NEVER (503 is odd). Its 5-level
# hierarchy bottoms out at 377 x 15 x 503 = 2.8 M cells -- a "coarse" grid holding 1/64 of the fine
# one. Rounding to the nearest nice number instead (2406 x 383 x 802 at 16 GPUs) is worse still:
# 2 levels, a 185 M-cell bottom. So the ladder below keeps the box shape at a clean 6 : 1 : 2
# (12H x 2H x 4H, against MKM's 12.57 x 2 x 4.19 -- a 4.5 % smaller box in x and z) and takes GNY
# through values rich in twos. Every dimension halves at least 5 times:
#
#   GPUs  GNY  Delta+       grid             Mcells  M/GPU  halvings x/y/z
#      1  160    2.25   960 x 160 x  320       49.2   49.2      6/5/6
#      2  192    1.88  1152 x 192 x  384       84.9   42.5      7/6/7
#      4  256    1.41  1536 x 256 x  512      201.3   50.3      9/7/8
#      8  320    1.13  1920 x 320 x  640      393.2   49.2      7/6/7
#     16  384    0.94  2304 x 384 x  768      679.5   42.5      8/7/8
#     32  512    0.70  4096 x 512 x  704     1476.4   46.1     11/8/6   <- longer box, see below
#
# 16 GPUS IS THE CEILING FOR A PROPERLY-SHAPED CHANNEL, and it is structural, not a queue limit.
# The wall-normal direction cannot be decomposed (a no-slip domain wall plus an internal y block
# boundary decouples the halves at the centreline; the driver hard-aborts), so the ORB has only the
# x-z plane to cut. At a 12H x 2H x 4H box the blocks are already cube-like at 16 ranks and the 32nd
# bisection picks y (checked: 3072 x 512 x 1024 on 32 ranks splits y on all 32). Reaching 32 GPUs
# needs a LONGER box -- the 32-GPU rung above is 16H x 2H x 2.75H, not 12H x 2H x 4H -- so it is a
# slightly different problem and should be read as such. Past that, the fix is wall-normal
# decomposition support in the solver, not a bigger allocation.
#
# Cells/GPU cannot be held exactly constant while keeping both the box shape and the factors of two
# (refining 3-D in powers of two moves the cell count in 8x steps), so it swings +-8 %. Weak
# efficiency is therefore computed from throughput PER GPU, which corrects for it exactly.
# MGLEVELS=8 everywhere and the hierarchy stops where the grid stops -- but note the distributed
# depth is set by the PER-RANK BLOCK, not the global grid: a level coarsens an axis only if every
# rank's block origin and size are even on it, so the coarsest global grid grows with the rank
# count. That is what the `amg` lever (agglomerated GraphAMG bottom solve) exists to fix.
# Verified against the real ORB at every rung: y is never split, block imbalance under 2 %.
case "$ARG" in refine|refine:*)
  ONLY="${ARG#refine}"; ONLY="${ONLY#:}"     # `refine:8` = just that rung (queue-parallel safe)
  # CPG forcing (CFR=0), matching the production GPU script; PMAXIT raised so the pressure iteration
  # count is a MEASUREMENT rather than a clamp — a cap that never binds changes nothing, a cap that
  # binds invalidates the timing (the first weak sweep sat at exactly 80 for N>=8).
  export CFR=0 PMAXIT=400 MGLEVELS=8
  for spec in 1:960:160:320 2:1152:192:384 4:1536:256:512 \
              8:1920:320:640 16:2304:384:768 32:4096:512:704; do
    IFS=: read -r N gx gy gz <<< "$spec"          # N:GNX:GNY:GNZ
    [ "$N" -le "$MAXN" ] || continue
    [ -z "$ONLY" ] || [ "$ONLY" = "$N" ] || continue
    FIXED_GNX=$gx; export GNY=$gy GNZ=$gz
    run_one "$N" "refine_np${N}${TAG}.json"
    # At the top rung, two probes of the block-local coarse grid: an agglomerated bottom solve,
    # and the coarse-first decomposition (partition the coarsened grid and refine it upward, so the
    # hierarchy nests for the full depth instead of stopping where a block turns odd).
    if [ "$N" = "$MAXN" ]; then
      run_one "$N" "refine_np${N}_amg${TAG}.json"    env GRAPHAMG=1
      run_one "$N" "refine_np${N}_decomp${TAG}.json" env PECLET_FLOW_DECOMP_LEVELS=8
    fi
  done
  FIXED_GNX=0
  echo "done -> $RES"; exit 0
esac
# OPTIONAL strong scaling: the ONE-GPU box (46.4M) split over more and more GPUs, down to 5.8M
# cells/GPU at N=8 — where the pressure solve's global reductions dominate the shrinking local work.
# 384/N stays a multiple of the MG coarsen-alignment (16) up to N=8, so blocks stay even.
if [ "$ARG" = strong ]; then
  FIXED_GNX=$BASE_GNX
  for N in 1 2 4 8; do
    [ "$N" -le "$MAXN" ] && run_one $N "chan_strong_np${N}${TAG}.json"
  done
  echo "done -> $RES"; exit 0
fi
# DIAGNOSTIC PROBES. The first weak sweep found the pressure solve pinned at PMAXIT=80 for N>=8 —
# so it never converged and the timings were clamped, not scaled. These four probes separate the
# possible causes; each is a couple of minutes. Run with 2 nodes.
if [ "$ARG" = probe ]; then
  # A. DECOMPOSITION or DOMAIN? A weak sweep grows both at once. Same global box, more ranks: if the
  #    iteration count stays put, convergence is decomposition-independent and the weak-sweep growth
  #    is the domain getting 32x longer under a fixed 5-level V-cycle.
  FIXED_GNX=$BASE_GNX
  for N in 1 2 4 8; do
    [ "$N" -le "$MAXN" ] && run_one $N "probe_strong_np${N}${TAG}.json"
  done
  FIXED_GNX=0
  # B. Is the 25-iteration SINGLE-GPU baseline the odd GNZ=503, which can never coarsen (so every
  #    V-cycle level carries all 503 z-cells and no coarse grid ever sees a z mode)? 512 can.
  run_one 1 "probe_evenz_np1${TAG}.json"     env GNZ=512
  run_one 8 "probe_evenz_np8${TAG}.json"     env GNZ=512
  # C. What does the solve actually cost when allowed to CONVERGE? (iteration count becomes a
  #    measurement instead of a clamp; also tells us how far from converged the capped runs were)
  for N in 1 8; do
    [ "$N" -le "$MAXN" ] && run_one $N "probe_uncapped_np${N}${TAG}.json" env PMAXIT=400
  done
  # D. Does MG depth scaled WITH the domain fix the growth? At N=8, 5 levels leave the coarsest x at
  #    192 cells — nowhere near a coarse solve. 8 levels take it to 24.
  run_one 8 "probe_deep_np8${TAG}.json"      env MGLEVELS=8 PMAXIT=400
  echo "done -> $RES"; exit 0
fi
if [ -n "$ARG" ] && [ "$ARG" != levers ]; then
  [ "$ARG" -le "$MAXN" ] || { echo "FATAL: N=$ARG needs $(( (ARG+3)/4 )) nodes, allocated $SLURM_NNODES" >&2; exit 1; }
  run_one "$ARG" "chan_np${ARG}${TAG}.json"
else
  for N in 1 2 4 8 16 32; do
    [ "$N" -le "$MAXN" ] && run_one $N "chan_np${N}${TAG}.json"
  done
fi

# Ablation at the largest allocated N — the channel-specific suspects, one variable at a time:
#   cpg       CFR forcing off (constant pressure gradient) = the forcing Allreduce removed
#   meanall   legacy pressure mean-removal scope (~3x more global reductions per Krylov iteration)
#   mg4/mg6   multigrid depth: GNZ=503 is odd and never coarsens, so the coarse levels are
#             semi-coarsened slabs — does more/less depth help or hurt at scale?
#   hoststage GPU-aware MPI off (halos staged through host memory)
if [ "$ARG" = levers ] || [ "${LEVERS:-0}" = 1 ]; then
  run_one $MAXN "chan_np${MAXN}_cpg${TAG}.json"       env CFR=0
  run_one $MAXN "chan_np${MAXN}_meanall${TAG}.json"   env MEANSCOPE=all
  run_one $MAXN "chan_np${MAXN}_mg4${TAG}.json"       env MGLEVELS=4
  run_one $MAXN "chan_np${MAXN}_mg6${TAG}.json"       env MGLEVELS=6
  run_one $MAXN "chan_np${MAXN}_hoststage${TAG}.json" env PECLET_CORE_GPU_AWARE_MPI=0
fi
echo "done -> $RES"
