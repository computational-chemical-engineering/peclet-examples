# Snellius run pack — channel-DNS scaling

One script, `chan_weak_gpu.sh`. It submits from **this** directory, writes JSONs straight into
`../results/snellius-h100/` (same relative path as in the repo, so `rsync` is a one-liner), and is
**resumable**: a point whose JSON already exists is skipped.

The measurement is the production turbulent-channel DNS (`examples/wall-bounded-turbulence/channel_dns_mpi.py`)
at Re_τ=180 on the Δ⁺=1.5 cross-section, instrumented like the TGV benchmark: per-phase device-fenced
timers, pressure iteration count, pressure-solve `MPI_Allreduce` time and count, and the CFR forcing's
own all-reduce, written as JSON.

## 0. Rebuild first — this is not optional

`flow` is header-only, so a stale `build_cuda_mpi` silently benchmarks the **old solver** and, worse,
lacks the driver APIs the instrument calls (`last_step_timers`, `set_pressure_mean_removal`, the
momentum tolerance stop) — every run then dies with a `TypeError`/`AttributeError` and writes no JSON.

```bash
ssh snellius
cd /projects/0/prjs1022/peclet/suite && git pull --recurse-submodules
cd ../peclet-examples && git pull
cd examples/wall-bounded-turbulence
sbatch install_snellius.sh h100      # -> flow/build_cuda_mpi ; note the job id as $BUILD
```

| what | path |
|---|---|
| suite (solver + submodules) | `/projects/0/prjs1022/peclet/suite` |
| this repo | `/projects/0/prjs1022/peclet/peclet-examples` |
| GPU build (H100) | `$SUITE/flow/build_cuda_mpi` (override with `BUILD=`) |
| venv (nanobind + mpi4py + **cupy**) | `$SUITE/flow/.venv` — cupy is required, CFR forcing shifts the field on device |
| results | `benchmarks/channel-scaling/results/snellius-h100/` |

## 1. The weak sweep, 1 → 32 GPUs

Each job measures **only its argument**, so they are queue-parallel safe and can all be submitted at
once. 46.4 M cells per GPU, `GNX = 384·N` × 240 × 503 — every rank owns exactly 384×240×503.

```bash
cd ../../benchmarks/channel-scaling/snellius
sbatch --dependency=afterok:$BUILD --nodes=1 chan_weak_gpu.sh 1
sbatch --dependency=afterok:$BUILD --nodes=1 chan_weak_gpu.sh 2
sbatch --dependency=afterok:$BUILD --nodes=1 chan_weak_gpu.sh 4
sbatch --dependency=afterok:$BUILD --nodes=2 chan_weak_gpu.sh 8
sbatch --dependency=afterok:$BUILD --nodes=4 chan_weak_gpu.sh 16
sbatch --dependency=afterok:$BUILD --nodes=8 chan_weak_gpu.sh 32
```

**32 GPUs is the ceiling for this case**, and it is physics, not queue budget: the ORB must never
split the wall-normal `y` (a no-slip domain wall plus an internal `y` block boundary decouples the two
halves at the centreline — the driver hard-aborts with `FATAL: ORB split the wall-normal y`). Weak
scaling grows only `x`, so `y` stays whole well past 32; beyond that the streamwise box gets long
enough that the decomposition starts looking for other axes.

Each point is ~140 steps ≈ 2–4 minutes of GPU time; the 40-minute walltime is for queue backfill, not
because the run needs it.

### Repeat draws (recommended at the inter-node points)

Node-set variability on Snellius is real. The second argument is a result tag — and it is **not
decoration**: `run_one` skips an existing JSON, so without a new tag a re-run silently re-reports the
old file.

```bash
sbatch --nodes=2 chan_weak_gpu.sh 8  r2
sbatch --nodes=4 chan_weak_gpu.sh 16 r2
sbatch --nodes=8 chan_weak_gpu.sh 32 r2
```

## 2. Lever ablation (one variable at a time, at the allocated max N)

```bash
sbatch --nodes=2 chan_weak_gpu.sh levers      # at N=8
sbatch --nodes=4 chan_weak_gpu.sh levers      # at N=16
```

| lever | what it isolates |
|---|---|
| `cpg` | CFR forcing off → the forcing's own global all-reduce, outside the pressure solve |
| `meanall` | legacy pressure mean-removal scope (~3× more global reductions per Krylov iteration) |
| `mg4` / `mg6` | multigrid depth — `GNZ=503` is odd and never coarsens, so coarse levels are semi-coarsened slabs |
| `hoststage` | GPU-aware MPI off (halos staged through host memory) |

## 3. Optional: strong scaling

The one-GPU box (46.4 M) split over more GPUs, down to 5.8 M cells/GPU:

```bash
sbatch --nodes=2 chan_weak_gpu.sh strong
```

## 4. Watch, then bring it home

```bash
squeue -u $USER -o '%.10i %.14j %.2t %.10M %.6D %R'
# The JSON is the ONLY success criterion — sacct reports COMPLETED for a job whose run failed.
ls ../results/snellius-h100/*.json
grep -H '"pressure_iters_per_step"' ../results/snellius-h100/chan_np*.json   # read this first
```

`pressure_iters_per_step` flat across rank counts is the falsifiable prediction; if it climbs with
`N`, the curve is an algorithmic effect, not a communication one, and `phase_seconds_per_step` says
which phase pays.

```bash
# LOCALLY:
rsync -av snellius:/projects/0/prjs1022/peclet/peclet-examples/benchmarks/channel-scaling/results/ \
  ~/Codes/peclet-examples/benchmarks/channel-scaling/results/
cd ~/Codes/peclet-examples/benchmarks/channel-scaling && python plot_scaling.py
```
