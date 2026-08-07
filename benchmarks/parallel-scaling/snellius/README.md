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
BUILD_CANS=1 sbatch --nodes=1 refs_genoa.sh
```

## 1. GPU weak scaling 1–32 H100 (task: extend the curve + per-phase split)

```bash
sbatch --nodes=1 tgv_weak_gpu.sh      # N=1,2,4      (~15 min)
sbatch --nodes=2 tgv_weak_gpu.sh      # N=8
sbatch --nodes=4 tgv_weak_gpu.sh      # N=16
sbatch --nodes=8 tgv_weak_gpu.sh      # N=32
# lever ablation (Chebyshev / GraphAMG bottom / host-staged halo) at the allocated max N:
LEVERS=1 sbatch --nodes=2 tgv_weak_gpu.sh
LEVERS=1 sbatch --nodes=4 tgv_weak_gpu.sh
```

Cost: each N is a ≲2-minute measurement; the whole campaign is a few k SBU.

## 2. Genoa CPU

```bash
sbatch --nodes=1 tgv_genoa.sh                       # hybrid mix sweep (192x1 … 12x16)
# then weak scaling at the winning mix (default 96x2):
for n in 1 2 4 8; do MODE=weak sbatch --nodes=$n tgv_genoa.sh; done
```

## 3. References

```bash
for n in 1 2 4; do CODE=cans sbatch --nodes=$n refs_genoa.sh; done
for n in 1 2; do CODE=openfoam sbatch --nodes=$n refs_genoa.sh; done   # serial blockMesh caps size
```

## 4. Bring results home

```bash
rsync -av snellius:/projects/0/prjs1022/peclet/peclet-examples/benchmarks/parallel-scaling/snellius/results/ \
  ~/Codes/peclet-examples/benchmarks/parallel-scaling/results/
```

Then regenerate figures locally (`plot_workstation.py` + the Snellius plot script) and rebuild the
page.
