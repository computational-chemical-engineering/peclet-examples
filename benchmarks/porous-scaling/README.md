# Porous-bed parallel scaling — Snellius runbook

Stokes permeability through DEM-grown random sphere packings (φ = 0.50), cut-cell **and**
ghost-cell IBM, on `gpu_h100` (4× H100 94GB per node). Two ladders:

- **Upscale** (`snellius/spheres_weak_gpu.sh`): classic weak scaling — 256³ cells/GPU fixed,
  domain and packing grow with N (1 → 32 GPUs, per-rung seeded beds, R = 16 cells).
- **Refine** (`snellius/spheres_refine_gpu.sh`): ONE fixed bed (16³ R-units, seed 100, committed
  at `results/packings/`), grid refined 256³ → 1024³ with N. Physics payoff: k(N) → k∞ per IBM
  (Richardson) + the cut-cell/ghost cross-check; R spans 16 → 64 cells.

Each rung runs **both IBMs** and writes one JSON per (ladder, N, ibm) — same schema as the TGV
`parallel-scaling` study, so the plotting conventions port over.

## 0. One-time setup (workstation → Snellius)

Push everything the study needs (flow carries the agglomerated-bottom fix + `auto` default):

```bash
cd ~/Codes/suite/flow && git push          # 56e1b7f + 3493a89
cd ~/Codes/suite      && git push          # docs + submodule pointers
cd ~/Codes/peclet-examples && git push     # this benchmark
```

On Snellius, refresh the suite + rebuild the MPI flow module with the existing installer
(pulls the umbrella, syncs submodules, re-bootstraps Kokkos, rebuilds `flow/build_cuda_mpi`,
rebuilds the venv incl. mpi4py against the loaded OpenMPI):

```bash
cd <peclet-examples>/examples/wall-bounded-turbulence
sbatch install_snellius.sh h100            # -> peclet-build-<jobid>.out; check has_mpi: True
```

Build **dem** (needed by the upscale ladder's per-rung packing; the refine ladder uses the
committed bed and never touches it). Same toolchain, same venv, same Kokkos prefix — ArborX is
already in it:

```bash
source <peclet-examples>/examples/wall-bounded-turbulence/snellius_env.sh   # MUST come first: nvcc!
SUITE=/projects/0/prjs1022/peclet/suite
source $SUITE/flow/.venv/bin/activate
which nvcc && python -m nanobind --cmake_dir     # both must succeed BEFORE configuring
PYINC=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
rm -rf $SUITE/dem/build_cuda                     # stale caches poison Python + Kokkos (below)
cmake -S $SUITE/dem -B $SUITE/dem/build_cuda -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=$SUITE/extern/install/nvidia-cuda \
  -DPython_EXECUTABLE=$SUITE/flow/.venv/bin/python -DPython_INCLUDE_DIR=$PYINC
cmake --build $SUITE/dem/build_cuda -j16
ls $SUITE/dem/build_cuda/peclet/dem/   # the module the bench imports via DEM_BUILD
```

**Check the configure output before building** — dem's `PecletDeps.cmake` is wheel-oriented and
*silently falls back* when a dependency isn't found, instead of failing:

- `[peclet] nanobind from ...flow/.venv/...` — if the path is the base `/sw/.../Python` install,
  the venv interpreter wasn't picked up (see cache note below).
- NO `[peclet] building+installing kokkos` line, and Kokkos reporting device `CUDA` — if
  `nvcc` is absent (env not sourced), `find_package(Kokkos)` against the CUDA prefix FAILS and
  PecletDeps FetchContent-builds a vendored **OpenMP+Serial host Kokkos** without erroring.

Two gotchas already hit in practice:
- `-DPython_EXECUTABLE` with capital P — the lowercase spelling is silently ignored and CMake
  falls back to the system python, which has no nanobind.
- FindPython's artifact variables are **sticky**: once a build dir has configured (even
  unsuccessfully) with the wrong interpreter, re-running with `-DPython_EXECUTABLE` changes
  nothing — hence the unconditional `rm -rf` above.

Optional pre-flight — every rung of both ladders was already verified at imbalance 1.000 with
full MG depth, but any new (grid, np) combination can be checked without a GPU:

```bash
PYTHONPATH=$SUITE/flow/build_cuda_mpi python $SUITE/flow/scripts/check_decomposition.py \
  --grid 1024,1024,512 --levels 7 --np 32 --mode 0
```

## 1. Submit

**Submit from inside `snellius/`** — the scripts resolve `../spheres_bench.py`,
`../results/packings` and the shared `snellius_env.sh` relative to `SLURM_SUBMIT_DIR`.
One job per rung (queue-parallel safe; a rung's packing seed is unique to it):

```bash
cd <peclet-examples>/benchmarks/porous-scaling/snellius

# Upscale ladder (256^3 cells/GPU; each job = cutcell + ghost at that N):
sbatch --nodes=1 spheres_weak_gpu.sh 1
sbatch --nodes=1 spheres_weak_gpu.sh 2
sbatch --nodes=1 spheres_weak_gpu.sh 4
sbatch --nodes=2 spheres_weak_gpu.sh 8
sbatch --nodes=4 spheres_weak_gpu.sh 16
sbatch --nodes=8 spheres_weak_gpu.sh 32

# Refine ladder (one bed, 256^3 -> 1024^3):
sbatch --nodes=1 spheres_refine_gpu.sh 1
sbatch --nodes=1 spheres_refine_gpu.sh 2
sbatch --nodes=1 spheres_refine_gpu.sh 4
sbatch --nodes=2 spheres_refine_gpu.sh 8
sbatch --nodes=4 spheres_refine_gpu.sh 16
sbatch --nodes=8 spheres_refine_gpu.sh 32

# Ablations at max N, after (or alongside) the 32-GPU rung:
#   smoother bottom  -> quantifies the agglomerated bottom's at-scale win, both IBMs
#   host-staged MPI  -> isolates the GPU-aware-MPI gain
sbatch --nodes=8 spheres_weak_gpu.sh levers
```

Every job is **resumable**: finished JSONs are skipped, so a timeout or node failure is fixed by
resubmitting the same line. After ANY solver change, pass a tag as argument 2
(`sbatch --nodes=1 spheres_weak_gpu.sh 1 mgfix2`) — otherwise the stale JSONs are kept.

Budget: phase A is 5+25 steps, the march ≤400; on H100s a cut-cell rung is minutes and ghost
tens of minutes, so the 1 h limit holds each job with headroom. Whole nodes are allocated
(4 GPUs even for the N=1,2 rungs), so the full study charges roughly 50–100 H100-hours,
dominated by the ghost marches and the multi-node rungs.

## 2. What to look for while it runs

```bash
grep -E "^\[(cfg|sdf|perf|march)" results/snellius-h100/*.log
```

- `[sdf]` voxel solid fraction ≈ the packing φ (0.500x) on every rung — the analytic SDF
  resampled correctly.
- `[perf] pressure iters/step` ≈ **flat across N** on each ladder — that is the agglomerated
  bottom + aligned decomposition doing their job (this is the headline claim of the study).
  Workstation reference at 128³, R=8: cut-cell ~12, ghost ~66.
- `[march] ... k/R^2` — upscale: k varies a little between rungs (different random beds, same φ);
  refine: k marches monotonically toward k∞ per IBM, cut-cell and ghost converging toward each
  other (workstation: 10.7% apart at R=5 → 2.1% at R=12).
- Reference values, seed-100 bed at 128³ (any decomposition must reproduce them to ~1e-10):
  cut-cell k/R² = 0.0109254 (140 steps), ghost 0.0113649 (75 steps).

## 3. Collect + plot

Back on the workstation:

```bash
cd ~/Codes/peclet-examples/benchmarks/porous-scaling
scp -r snellius:<...>/porous-scaling/snellius/results/snellius-h100 results/
scp 'snellius:<...>/porous-scaling/results/packings/*.npz' results/packings/  # the per-rung beds
python plot_spheres.py            # throughput/efficiency/iters + k(N) with Richardson fit
quarto preview index.qmd          # the study page
```

Commit the JSONs + packings (they are the reproducibility record; the logs are not committed).

## Gotchas (learned the hard way)

- **Do NOT pack beds with `dem/build_cuda` on Snellius** until the H100 corruption bug is fixed:
  the CUDA 12.6/sm_90 build silently fails to resolve contacts for some box/φ configurations
  (deterministic; probe_dem2/3 in `snellius/`) — spheres grow through each other and only the
  voxel gate catches it. Pack with the CPU build instead: `DEM_BUILD=$SUITE/dem/build_omp`
  (probe_dem3 builds it; 16-core packing is faster than the failing GPU runs at these N anyway).
  Workstation (CUDA 13.2/sm_120) packing is unaffected.

- `WARMSTART=1` **diverges** the steady Stokes march (open solver bug) — the bench defaults it
  off; do not switch it on for these runs.
- SURF's sbatch drops leading `VAR=x sbatch ...` env vars — rung selection is a positional
  argument for that reason. `SUITE`/`BUILD`/`GPU_AWARE` overrides must be exported beforehand.
- FindMPI vs mpi4py: both build and run source the same `snellius_env.sh`, so the OpenMPI that
  mpi4py linked against is the one `srun --mpi=pmix` launches. Don't mix module stacks.
- The refine 1024³ rung holds ~0.5 B cells over 32 GPUs (~16 M cells/GPU + MG hierarchy +
  IBM overlay) — comfortable on 94 GB H100s; do not try it on smaller cards.
