#!/bin/bash
# ==========================================================================================
# Turbulent channel-flow DNS (Re_tau=180) on Snellius GPU nodes — a converged MKM-1999 benchmark run.
#
#   Full MKM box 4piH x 2H x (4/3)piH, isotropic grid.  Delta+ = 360/GNY.  Resolution presets:
#     GNY=240  Delta+=1.5  1508x240x503  = 182M cells  -> 1 H100 node (4 GPU, 45M/rank)   [default]
#     GNY=288  Delta+=1.25 1810x288x603  = 314M cells  -> 2 H100 nodes (8 GPU, 39M/rank)
#     GNY=360  Delta+=1.0  2262x360x754  = 614M cells  -> 3 H100 nodes (12 GPU, 51M/rank)  [hero]
#   Higher resolution => less numerical dissipation => closer to MKM (see the example page). Pick a
#   preset with GNY=... and match --nodes so per-rank cells stay <~50M (94GB H100).
#
#   CONVERGED STATISTICS: this is a long run. It CHECKPOINTS every CKPT steps and AUTO-RESUMES: the job
#   queues its own successor (SLURM afterany dependency) before running, so when the walltime limit hits,
#   a new job automatically starts from the checkpoint (fields + accumulators + step counter restored).
#   The chain stops itself when the driver reaches NSTEPS (writes ${OUT}.done) or after CHAIN resubmits.
#   So you submit ONCE and walk away. Averaging (prof_*) begins at STATSTART (set past the u_tau plateau,
#   ~5 eddy-turnovers); at ~1.7 s/step for 182M/4GPU a converged average is ~40-50k steps (~20-24h),
#   spread over however many walltime windows it takes.
#
#   Submit ONCE:  OUT=chan240 sbatch snellius_gpu.slurm                    # 182M, 1 node
#                 OUT=chan360 GNY=360 sbatch --nodes=3 snellius_gpu.slurm  # 614M hero, 3 nodes
#   Watch:  squeue --me   (you'll see the running job + a PENDING successor with dependency)
#   Stop early:  scancel the pending successor, or `touch ${OUT}.done`.  Manual mode: CHAIN=0.
#   Confirm on the machine: `sinfo -s` (partitions), `module avail 2024` (versions), `accinfo` (account).
# ==========================================================================================
#SBATCH --job-name=chan-dns
#SBATCH --partition=gpu_h100          # H100 (4x94GB, 64c). A100: --partition=gpu_a100 (4x40GB, 72c).
#SBATCH --nodes=1                     # match to the resolution preset above (per-rank <~50M cells)
#SBATCH --gpus-per-node=4
#SBATCH --ntasks-per-node=4           # one MPI rank per GPU
#SBATCH --cpus-per-task=16            # 64 cores / 4 (gpu_h100).  Use 18 on gpu_a100 (72/4).
#SBATCH --time=24:00:00               # long averaging run; max 120:00:00. Resubmit resumes on timeout.
#SBATCH --output=chan-dns-%j.out
#SBATCH --account=tes24005
set -euo pipefail

# --- environment: MUST match the toolchain used to BUILD (see install_snellius.sh) -------------
source "${SLURM_SUBMIT_DIR:-$PWD}/snellius_env.sh"   # 2024a GPU-aware stack; sets OMPI_MCA_pml=ucx etc.

SUITE="${SUITE:-/projects/0/prjs1022/peclet/suite}"
BUILD="${BUILD:-$SUITE/flow/build_cuda_mpi}"            # the PECLET_FLOW_MPI=ON CUDA build
VENV="${VENV:-$SUITE/flow/.venv}"
export PYTHONPATH="$BUILD:${PYTHONPATH:-}"

# --- problem size (Delta+ = 360/GNY) -----------------------------------------------------------
export GNY="${GNY:-240}"
export GNX="${GNX:-$(python3 -c "import math;print(round(2*math.pi*$GNY))")}"   # 4piH -> 2pi*GNY
export GNZ="${GNZ:-$(python3 -c "import math;print(round(2*math.pi/3*$GNY))")}" # (4/3)piH -> (2pi/3)*GNY
# Forcing: CPG (constant pressure gradient, body force) is the DEFAULT for the production/spin-up —
# it pins u_tau=1 exactly (Re_tau=180 by construction, matching MKM) and robustly sustains transition.
# Under CPG a laminarizing flow shows as the bulk U_b+ climbing toward ~60 (turbulent ~15.7). Set
# CFR=15.68 instead to hold the bulk (constant flow rate) once the flow is turbulent.
export CFR="${CFR:-0}"
export NSTEPS="${NSTEPS:-50000}"     # total steps to reach (across resubmits); ~5-10 eddy-turnovers
export STATSTART="${STATSTART:-25000}" # begin time-averaging only after u_tau plateaus (~5 turnovers)
export STATEVERY="${STATEVERY:-25}"
export CKPT="${CKPT:-2000}"          # checkpoint every N steps -> resubmit resumes (survive walltime)
export DT="${DT:-0.02}" ; export DIAG="${DIAG:-500}" ; export ADV=0
# NB: keep OUT STABLE across resubmits so the run resumes from its checkpoint (do NOT use $SLURM_JOB_ID).
export OUT="${OUT:-chan_${GNY}}"

# --- auto-resubmit chain: continue across walltime limits with no manual action ------------------
# If the run already finished (driver wrote ${OUT}.done), stop. Otherwise queue a successor that runs
# AFTER this job ends (afterany) with the SAME allocation + environment, so on a walltime kill it
# resumes from the checkpoint. CHAIN caps the number of auto-resubmits (crash-loop guard).
# Disable with CHAIN=0 (then resubmit by hand). The successor's first action is this same check, so a
# normal completion just makes it exit immediately.
export CHAIN="${CHAIN:-12}"
if [ -f "${OUT}.done" ]; then
  echo "[chain] ${OUT} already complete ($(cat ${OUT}.done)); not resubmitting."; exit 0
fi
if [ "${CHAIN}" -gt 0 ]; then
  nxt=$(sbatch --parsable --dependency=afterany:${SLURM_JOB_ID} \
        --nodes=${SLURM_NNODES} --partition=${SLURM_JOB_PARTITION} \
        --export=ALL,CHAIN=$((CHAIN-1)) "${SLURM_SUBMIT_DIR}/snellius_gpu.slurm" 2>/dev/null) \
    && echo "[chain] queued successor job ${nxt} (starts after ${SLURM_JOB_ID}; ${CHAIN} resubmits left)" \
    || echo "[chain] WARNING: could not queue successor (submit by hand to resume)"
fi

# GPU binding: SLURM cgroup-isolates one GPU per task via the srun flags below, so the driver must
# NOT remap CUDA_VISIBLE_DEVICES. It prints each rank's TRUE physical GPU (host + PCI bus) at startup
# and WARNS if any GPU is shared -- check that line: every rank must be on a distinct GPU.
export PECLET_BIND_GPU=0
# GPU-aware MPI: device pointers straight into the halo (2024a stack has CUDA-aware UCX-CUDA, validated
# by check_gpu_aware_mpi.sh). snellius_env.sh already set OMPI_MCA_pml=ucx + UCX_MEMTYPE_CACHE=n.
# Set =0 to fall back to host-staging (always correct) if you ever change the MPI stack.
export PECLET_CORE_GPU_AWARE_MPI=1

echo "grid ${GNX}x${GNY}x${GNZ}  ranks=$SLURM_NTASKS  nodes=$SLURM_NNODES"
srun --mpi=pmix --gpus-per-task=1 --gpu-bind=per_task:1 "$VENV/bin/python" channel_dns_mpi.py
echo "done -> ${OUT}_stats.npz  (post-process: python analyze_channel.py ${OUT}_stats.npz out.png)"
