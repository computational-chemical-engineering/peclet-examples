# Snellius run pack — parallel-scaling study

All scripts submit from this directory, write JSONs into `results/snellius-*/`, and are
**resumable** (existing JSONs are skipped — delete a JSON to re-measure it). Keep walltimes
short: `gpu_h100` is usually full and short jobs backfill in hours instead of days.

## 0. One-time setup

```bash
cd /projects/0/prjs1022/peclet/suite && git pull --recurse-submodules
cd ../peclet-examples && git pull
# GPU build (existing recipe): FRESH=1 sbatch examples/wall-bounded-turbulence/install_snellius.sh h100
# CPU build for genoa (OpenMP backend + MPI), once:
#   bootstrap host-openmp prefix, then in suite/flow:
#   cmake -S . -B build_omp_mpi -DPECLET_FLOW_MPI=ON \
#         -DCMAKE_PREFIX_PATH=$PWD/../extern/install/host-openmp \
#         -DPython_EXECUTABLE=$PWD/.venv/bin/python && cmake --build build_omp_mpi -j
# CaNS build, once:
sbatch --nodes=1 refs_genoa.sh build
```

**Mode selection is always a script ARGUMENT, never a leading env var** — SURF's sbatch drops
those (the channel campaign's FRESH=1 lesson). `sbatch ... tgv_genoa.sh weak`, `refs_genoa.sh
cans`, `tgv_weak_gpu.sh levers`.

## 1. GPU weak scaling 1–32 H100 (task: extend the curve + per-phase split)

**The GPU build must be rebuilt first** (the driver needs the tolerance-stop / mean-removal APIs
from the perf commits — an older `build_cuda_mpi` fails every run with a TypeError):

```bash
cd /projects/0/prjs1022/peclet/suite && git pull --recurse-submodules
cd ../peclet-examples/examples/wall-bounded-turbulence
sbatch install_snellius.sh h100          # incremental flow rebuild; note the job id -> $BUILD
```

Then queue the whole campaign with dependencies (each job measures ONLY its argument N —
queue-parallel safe):

```bash
cd ../../benchmarks/parallel-scaling/snellius
sbatch --dependency=afterok:$BUILD --nodes=1 tgv_weak_gpu.sh 1
sbatch --dependency=afterok:$BUILD --nodes=1 tgv_weak_gpu.sh 2
sbatch --dependency=afterok:$BUILD --nodes=1 tgv_weak_gpu.sh 4
sbatch --dependency=afterok:$BUILD --nodes=2 tgv_weak_gpu.sh 8
sbatch --dependency=afterok:$BUILD --nodes=4 tgv_weak_gpu.sh 16
sbatch --dependency=afterok:$BUILD --nodes=8 tgv_weak_gpu.sh 32
# lever ablation (Chebyshev / mean-scope-all / GraphAMG bottom / host-staged halo):
sbatch --dependency=afterok:$BUILD --nodes=2 tgv_weak_gpu.sh levers   # at N=8
sbatch --dependency=afterok:$BUILD --nodes=4 tgv_weak_gpu.sh levers   # at N=16
```

Cost: each N is a ≲2-minute measurement; the whole campaign is a few k SBU. gpu_h100 queue wait
dominates — short walltimes (45 min) backfill well.

## 2. Genoa CPU

```bash
sbatch --nodes=1 tgv_genoa.sh                       # hybrid mix sweep (192x1 … 12x16)
# then weak scaling at the winning mix (default 96x2). NOTE: mode is a script ARGUMENT —
# SURF sbatch drops leading env vars (the FRESH=1 lesson):
for n in 1 2 4 8; do sbatch --nodes=$n tgv_genoa.sh weak; done
```

## 3. References

```bash
sbatch --nodes=1 refs_genoa.sh incflo-build                       # once (AMReX superbuild, ~15 min)
sbatch --nodes=1 --time=03:00:00 refs_genoa.sh openfoam-build     # once (ESI v2412 source, ~1 h)
for n in 1 2 4; do sbatch --nodes=$n refs_genoa.sh cans; done
for n in 1 2 4; do sbatch --nodes=$n refs_genoa.sh incflo; done
for n in 1 2; do sbatch --nodes=$n refs_genoa.sh openfoam; done   # serial blockMesh caps size
```

## 4. Bring results home

```bash
rsync -av snellius:/projects/0/prjs1022/peclet/peclet-examples/benchmarks/parallel-scaling/snellius/results/ \
  ~/Codes/peclet-examples/benchmarks/parallel-scaling/results/
```

Then regenerate figures locally (`plot_workstation.py` + the Snellius plot script) and rebuild the
page.
