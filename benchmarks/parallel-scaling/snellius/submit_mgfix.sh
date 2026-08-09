#!/bin/bash
# ==========================================================================================
# Re-measure the peclet.flow scaling campaign after the MG residual-halo fix (flow 5d77deb).
#
# RUN THIS ON THE SNELLIUS LOGIN NODE (it only submits jobs; it is not itself a batch script):
#
#   ssh snellius
#   cd /projects/0/prjs1022/peclet/peclet-examples/benchmarks/parallel-scaling/snellius
#   bash submit_mgfix.sh all          # pull + build what is stale + queue every measurement
#
# What it does, in order:
#   1. `git pull` the suite (with submodules) and peclet-examples          (PULL=0 to skip)
#   2. for each backend it needs, checks whether flow's build is MISSING or OLDER than the
#      sources; if so it submits the build job and makes every measurement depend on it
#      (afterok). An up-to-date build is left alone and the jobs are queued immediately.
#   3. queues the measurements with the result tag $TAG (default "mgfix"), which keeps them
#      in separate JSONs from the pre-fix numbers -- the run scripts SKIP existing files, so
#      without a new tag you would silently re-report the old results.
#   4. prints the squeue watch command and the exact rsync line to pull results home.
#
# Modes:  all (default) | cpu | gpu | build   ("build" submits the builds and queues nothing)
#
# Env:
#   TAG=mgfix        result tag appended to every JSON (use mgfix2, mgfix3, ... for repeat draws)
#   REPEATS=1        2 => also queue a second draw of every genoa weak point as ${TAG}b
#                    (genoa node-set variability is REAL: same config measured 3.2 vs 8.0 s/step)
#   MAXGPU=32        largest GPU count in the weak sweep (1,2,4,8,16,32 -> up to 8 nodes)
#   DRY_RUN=1        print the sbatch lines instead of submitting
#   PULL=0           skip the git pulls (e.g. you already pulled a specific commit)
#   FORCE_BUILD=1    rebuild even if the build looks current
#
# The references (CaNS / incflo / OpenFOAM) do NOT need re-running: the fix touches peclet only.
# ==========================================================================================
set -uo pipefail

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
EXAMPLES="${EXAMPLES:-/projects/0/prjs1022/peclet/peclet-examples}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$EXAMPLES/examples/wall-bounded-turbulence"
TAG="${TAG:-mgfix}"
REPEATS="${REPEATS:-1}"
MAXGPU="${MAXGPU:-32}"
MODE="${1:-all}"
GPU_BUILD="$SUITE/flow/build_cuda_mpi"     # what tgv_weak_gpu.sh defaults to
CPU_BUILD="$SUITE/flow/build_omp_mpi"      # what tgv_genoa.sh defaults to

# Every run script derives its paths from SLURM_SUBMIT_DIR, which sbatch sets to the directory the
# submission was made FROM — so always submit from the pack directory, wherever the user invoked us.
cd "$HERE" || { echo "cannot cd to $HERE" >&2; exit 1; }
for f in tgv_genoa.sh tgv_weak_gpu.sh "$INSTALL_DIR/install_snellius.sh" \
         "$INSTALL_DIR/snellius_env.sh" ../tgv_bench.py; do
  [ -r "$f" ] || { echo "FATAL: missing $f (is EXAMPLES=$EXAMPLES right?)" >&2; exit 1; }
done

say() { echo "[submit_mgfix] $*"; }
sub() {  # echo + submit; job id goes to stdout (for --dependency) and to the log (for the user)
  echo "  sbatch $*" >&2
  local id
  if [ "${DRY_RUN:-0}" = 1 ]; then id=DRYRUN; else id=$(sbatch --parsable "$@") || id=""; fi
  [ -n "$id" ] && echo "    -> job $id" >&2 || echo "    -> SUBMIT FAILED" >&2
  echo "$id"
}

# --- 1. sources -------------------------------------------------------------------------------
if [ "${PULL:-1}" = 1 ]; then
  say "pulling $SUITE (with submodules)"
  git -C "$SUITE" pull --ff-only && git -C "$SUITE" submodule update --init --recursive
  say "pulling $EXAMPLES"
  git -C "$EXAMPLES" pull --ff-only
fi
say "flow at $(git -C "$SUITE/flow" log --oneline -1)"

# --- 2. builds --------------------------------------------------------------------------------
# Stale = no module, or a source file newer than it. `git pull` stamps checked-out files with the
# pull time, so this catches exactly "the solver changed since this build".
needs_build() {
  local b="$1" so
  [ "${FORCE_BUILD:-0}" = 1 ] && return 0
  so=$(ls "$b"/peclet/flow/_flow*.so 2>/dev/null | head -1)
  [ -z "$so" ] && return 0
  [ -n "$(find "$SUITE/flow/src" "$SUITE/core/include" -newer "$so" -print -quit 2>/dev/null)" ]
}

CPU_JOB="" GPU_JOB=""
want_cpu=0 want_gpu=0
case "$MODE" in
  all)   want_cpu=1; want_gpu=1 ;;
  cpu)   want_cpu=1 ;;
  gpu)   want_gpu=1 ;;
  build) want_cpu=1; want_gpu=1 ;;
  *) echo "usage: $0 [all|cpu|gpu|build]" >&2; exit 2 ;;
esac

# The two builds share flow/.venv and the installer rebuilds it with --clear, so when BOTH are
# stale the CPU build goes first and the GPU build (which re-adds cupy) finishes the venv.
if [ "$want_cpu" = 1 ] && needs_build "$CPU_BUILD"; then
  say "CPU build $CPU_BUILD is missing/stale -> submitting genoa build"
  CPU_JOB=$(sub --job-name=peclet-build-cpu --partition=genoa --nodes=1 --ntasks=1 \
                --cpus-per-task=48 --time=02:00:00 --account=tes24005 \
                --output="$HERE/peclet-build-cpu-%j.out" \
                --wrap="cd '$INSTALL_DIR' && SLURM_SUBMIT_DIR='$INSTALL_DIR' bash ./install_snellius.sh cpu")
  say "  build job $CPU_JOB"
else
  [ "$want_cpu" = 1 ] && say "CPU build $CPU_BUILD is current -> no rebuild"
fi

if [ "$want_gpu" = 1 ] && needs_build "$GPU_BUILD"; then
  say "GPU build $GPU_BUILD is missing/stale -> submitting h100 build"
  gdep=""; [ -n "$CPU_JOB" ] && [ "$CPU_JOB" != DRYRUN ] && gdep="--dependency=afterok:$CPU_JOB"
  GPU_JOB=$(sub --job-name=peclet-build-gpu $gdep --partition=gpu_h100 --gpus=1 --nodes=1 \
                --ntasks=1 --cpus-per-task=16 --time=02:00:00 --account=tes24005 \
                --output="$HERE/peclet-build-gpu-%j.out" \
                --wrap="cd '$INSTALL_DIR' && SLURM_SUBMIT_DIR='$INSTALL_DIR' bash ./install_snellius.sh h100")
  say "  build job $GPU_JOB"
else
  [ "$want_gpu" = 1 ] && say "GPU build $GPU_BUILD is current -> no rebuild"
fi
[ "$MODE" = build ] && { say "build-only mode; nothing else queued"; exit 0; }

dep_of() {  # $1 = job id (may be empty) -> "--dependency=afterok:ID" or nothing
  [ -n "$1" ] && [ "$1" != DRYRUN ] && echo "--dependency=afterok:$1"
}

# --- 3. genoa CPU measurements -----------------------------------------------------------------
# The headline: does 12x16 (fat) now match 96x2 (thin) per node? The mix job answers it on ONE
# node; the weak sweeps answer whether it holds across nodes (fat ranks = 8x fewer ranks in the
# collectives, which is the whole point of the exercise).
if [ "$want_cpu" = 1 ]; then
  d=$(dep_of "$CPU_JOB")
  say "queueing genoa: 1-node mix + weak sweeps at 12x16 (fat) and 96x2 (thin), tag=$TAG"
  sub $d --nodes=1 --job-name=tgv-mix "$HERE/tgv_genoa.sh" mix "$TAG" >/dev/null
  for n in 1 2 4 8; do
    sub $d --nodes=$n --job-name=tgv-w${n}-fat --export=ALL,RPN=12,THREADS=16 \
        "$HERE/tgv_genoa.sh" weak "$TAG" >/dev/null
    sub $d --nodes=$n --job-name=tgv-w${n}-thin --export=ALL,RPN=96,THREADS=2 \
        "$HERE/tgv_genoa.sh" weak "$TAG" >/dev/null
  done
  if [ "$REPEATS" -ge 2 ]; then
    say "queueing second genoa draw (tag ${TAG}b)"
    for n in 1 2 4 8; do
      sub $d --nodes=$n --job-name=tgv-w${n}-fat2 --export=ALL,RPN=12,THREADS=16 \
          "$HERE/tgv_genoa.sh" weak "${TAG}b" >/dev/null
      sub $d --nodes=$n --job-name=tgv-w${n}-thin2 --export=ALL,RPN=96,THREADS=2 \
          "$HERE/tgv_genoa.sh" weak "${TAG}b" >/dev/null
    done
  fi
fi

# --- 4. H100 GPU measurements -------------------------------------------------------------------
# Single-device throughput went up ~1.75x, so the whole 1-32 weak curve moves. The lever ablation
# is worth redoing too: Chebyshev went 17 -> 5 iterations locally, and it was the lever the old
# ablation rejected (2.6x worse).
if [ "$want_gpu" = 1 ]; then
  d=$(dep_of "$GPU_JOB")
  say "queueing H100 weak sweep 1..$MAXGPU + lever ablation, tag=$TAG"
  for N in 1 2 4 8 16 32; do
    [ "$N" -le "$MAXGPU" ] || continue
    nodes=$(( (N + 3) / 4 ))
    sub $d --nodes=$nodes --job-name=tgv-gpu-$N "$HERE/tgv_weak_gpu.sh" "$N" "$TAG" >/dev/null
  done
  [ "$MAXGPU" -ge 8 ]  && sub $d --nodes=2 --job-name=tgv-gpu-lev8  "$HERE/tgv_weak_gpu.sh" levers "$TAG" >/dev/null
  [ "$MAXGPU" -ge 16 ] && sub $d --nodes=4 --job-name=tgv-gpu-lev16 "$HERE/tgv_weak_gpu.sh" levers "$TAG" >/dev/null
fi

# --- 5. what to do next --------------------------------------------------------------------------
cat <<EOF

[submit_mgfix] queued. Watch:
    squeue -u \$USER -o '%.10i %.14j %.2t %.10M %.6D %R'

Results land in (resumable — a rerun only fills gaps):
    $HERE/results/snellius-genoa/*_${TAG}*.json
    $HERE/results/snellius-h100/*_${TAG}*.json

Quick read on the login node — the fix's falsifiable prediction is that the fat and thin
configurations now agree on iteration count:
    grep -H '"pressure_iters_per_step"' $HERE/results/snellius-genoa/mix_*_${TAG}.json
    python3 -c "import json,glob;[print(f.split('/')[-1], round(json.load(open(f))['ms_per_step']), \\
      round(json.load(open(f))['mcells_per_s'],1), json.load(open(f))['pressure_iters_per_step']) \\
      for f in sorted(glob.glob('$HERE/results/snellius-*/*${TAG}*.json'))]"

Pull them home (run LOCALLY, from your laptop/workstation):
    rsync -av snellius:$HERE/results/ ~/Codes/peclet-examples/benchmarks/parallel-scaling/results/

Then regenerate figures + page locally:
    cd ~/Codes/peclet-examples/benchmarks/parallel-scaling
    python plot_snellius.py && python plot_workstation.py
EOF
