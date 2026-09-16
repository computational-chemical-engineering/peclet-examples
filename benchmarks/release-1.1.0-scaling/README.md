# peclet 1.1.0 scaling benchmark — runbook

The measurement behind the Zenodo deposit *Parallel performance of peclet.flow 1.1.0*
and the gallery page [`index.qmd`](index.qmd). Everything needed to reproduce it is in this
directory: the geometry, the driver, the cluster scripts, the raw results and the analysis.

## What is measured

**Creeping flow through a periodic random sphere packing with the cut-cell immersed boundary
method**, driven by a body force in a triply periodic box — `peclet.flow` 1.1.0, one MPI rank per
GPU or per core.

The physical unit of the study is one **unit cell**: 1043 spheres of radius R = 1 at solid
fraction φ = 0.45 in a cubic box of 21.333 R (`bed_phi0.45_r18_s0.npz`), resolved at 384³ cells,
i.e. **R = 18 cells** — above the R ≥ 16 at which the cut-cell permeability is converged to four
digits, so the physics gate measures the solver and not an under-resolved bed.

| Ladder | Machine | Configuration | Rungs |
|---|---|---|---|
| **W** weak | Snellius `gpu_h100` | 384³ cells per GPU, the unit cell tiled | 1 → 32 GPUs, 56.6 M → 1.81 Gcells |
| **S** strong | Snellius `genoa` | one unit cell, fixed 384³ | 24 → 1536 cores |
| **T** strong | Snellius `gpu_h100` | one unit cell, fixed 384³ | 1 → 32 GPUs |
| **N** control | both | Taylor–Green, no geometry, same grids | subset |

The weak ladder **tiles one unit cell**: rung N is an exact periodic replication of the same
problem, N times over. So the physics observable is not a scatter across independently packed beds
— it is one number every rung must reproduce.

## The correctness gate

Every run starts from rest and takes the *same* number of steps (WARMUP + NSTEPS = 13), so
**⟨u⟩ at the end is one number that every rung of every ladder must return**, on either machine, at
any rank count. It costs one allreduce and it is checked in `gates.md`. A run also refuses to start
if the SDF it sampled disagrees with the packing's solid fraction, and a rung whose pressure solve
touched its iteration cap is reported as capped rather than plotted as a timing.

The permeability itself (`MARCH_TOL=1e-5`, marched to steady state) is measured at a few rungs
only: it is a property of the unit cell, and the 13-step gate is the sharper per-rung check.

## Configuration

The **shipped 1.1.0 defaults** — MG-PCG at rtol 1e-8, coarse-level telescoping, the `auto`
agglomerated bottom, the velocity-multigrid auto rule, the coupled momentum tolerance, double
operator storage, and the shipped auto-detection of GPU-aware MPI (`PECLET_CORE_GPU_AWARE_MPI` is
deliberately left unset) — with **one stated exception**: the pressure multigrid depth is requested
as deep as the grid admits (`LEVELS=10`, which the solver clamps) instead of the shipped default
of 4. Depth is a property of the grid, not a tuning constant. `LEVELS=4` is measured at one rung as
the out-of-the-box sensitivity point.

## Reproducing it

The PyPI wheels **cannot** run this: MPI is a build-time option in flow and the published wheels
are single-rank. The study builds the released tag from source.

```bash
# 1. the unit cell (any machine; uses the RELEASED dem wheel, so pip is the only dependency)
python -m venv v && ./v/bin/pip install "peclet-dem==1.1.0" numpy
OMP_NUM_THREADS=8 OMP_PROC_BIND=false ./v/bin/python make_bed.py     # -> bed_phi0.45_r18_s0.npz

# 2. site build of v1.1.0 on Snellius, one tree per backend (~5 min each)
sbatch --nodes=1 --gpus-per-node=1 --ntasks-per-node=1 snellius/install_bench.sh v1.1.0 h100
sbatch -p genoa --gpus-per-node=0 -c 32 -t 02:00:00    snellius/install_bench.sh v1.1.0 cpu

# 3. the ladders (each rung names its own allocation: billing is per ALLOCATED GPU)
./snellius/submit_ladders.sh pilot        # go/no-go: 1 GPU, 4 GPUs, 192 cores
./snellius/submit_ladders.sh weak
./snellius/submit_ladders.sh strong-gpu
./snellius/submit_ladders.sh strong-cpu
./snellius/submit_ladders.sh tgv
./snellius/submit_ladders.sh march        # permeability
./snellius/submit_ladders.sh spread       # repeat allocations of the top rungs
./snellius/submit_ladders.sh levels       # the LEVELS=4 sensitivity point

# 4. tables, gates and figures from the raw JSON
python analyze.py results
```

A single rung, without Slurm:

```bash
PACK=bed_phi0.45_r18_s0.npz CASE=bed MODE=weak GPR=384 \
  mpirun -np 4 python scaling_bench.py
```

## Files

| File | What it is |
|---|---|
| `scaling_bench.py` | the driver — all four ladders, one JSON schema (`peclet-scaling-1`) |
| `make_bed.py`, `bed_phi0.45_r18_s0.npz` | the unit cell and the script that grew it |
| `snellius/install_bench.sh` | site build of the released tag (one tree per backend) |
| `snellius/run_gpu.sh`, `run_cpu.sh` | one rung each |
| `snellius/submit_ladders.sh` | queues a whole ladder with the right allocation per rung |
| `snellius/snellius_env.sh` | the 2024a toolchain every script agrees on |
| `analyze.py` | gates, tables and figures from `results/**/*.json` |
| `results/snellius-{h100,genoa}/` | raw per-run JSON **and the run logs** — the evidence |
| `gates.md`, `summary.md` | generated: the correctness gates and the results tables |
| `STATE.md`, `DECISIONS.md` | campaign position, and the decisions behind the design |
| `zenodo/` | deposit metadata and the packaging script |

## Caveats that belong with the numbers

- The CPU rungs take **exclusive** nodes, so the sub-node rungs (24, 48, 96) have up to 8× the
  memory bandwidth per rank of the full-node rungs. That flatters the baseline and therefore
  *understates* the efficiencies computed against it; the apples-to-apples segment is 192 → 1536.
- The weak ladder's large rungs are **periodic replications** of one unit cell, not independent
  beds. That is what makes the physics gate exact; it also means they are not a statement about
  bed-to-bed variability.
- Top-rung timings carry a node-placement spread; the `spread` ladder repeats them on separate
  allocations and `summary.md` reports the range rather than a single number.
