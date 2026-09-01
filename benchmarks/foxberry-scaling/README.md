# FoxBerry comparison scaling — runbook

Reproduces the two 3-D strong-scaling cases of FoxBerry's `scaling/Scaling.cpp` with
`peclet.flow`, so the numbers drop straight onto FoxBerry's own graphs
(`FoxBerry/scaling/scaling_single_phase_packed_bed.py`): loglog, x = number of processors,
y = **execution time per step [s]**, 64M cells, the ladder 24 … 1536.

Three **configurations**, each naming a (case, BC mode, bed) triple — those three are not
independent, so they are selected together by name:

| config | FoxBerry | here |
|---|---|---|
| **single** | Case 2, single-phase 3D flow | unit box, inlet u=1, outlet, 4 no-slip walls, ρ=1, μ=1, dt=Co·dx/u, 100 steps |
| **packed** | Case 3, packed-bed IBM | same box/BCs, inlet u=0.001, 5000 spheres at holdup 0.45, cut-cell IBM — **BLOCKED, see "Open issue"** |
| **packed-periodic** | (no FoxBerry counterpart) | the same bed and cell count, but **fully periodic and body-force driven**, on a triply-periodic bed — the valid way to price peclet's packed-bed step while `packed` is blocked |

`packed-periodic` is *not* a FoxBerry reproduction: the boundary conditions differ. It is the same
problem *size* (same cells, same 5000 spheres, same holdup, same sphere radius to 0.7 %), so it
prices the per-step cost of an IBM bed of that scale honestly, and it is the configuration to
report until the open issue is fixed. The plot labels it as such.

**The two beds are different artifacts and are not interchangeable.** FoxBerry places sphere
*centers* in [0.01, 0.99] with radius 0.0276, so its spheres are clipped by the inlet/outlet
planes and the bed is periodic in y/z only. Run *that* bed under periodic BCs and the geometry has
a broken seam at x=0/1 — a sphere cut at one face does not continue at the other, and the margins
become a clear slot spanning the whole cross-section, a short circuit for a body-force-driven
flow. So `packed-periodic` uses its own triply-periodic bed (`PERIODIC=1 make_bed.py`, holdup 0.45
over the full unit box, r = 0.0278004), and `foxberry_bench.py` **refuses** either mismatched
pairing rather than silently measuring it.

> **Status: `single` and `packed-periodic` run and are the reportable configurations; `packed`
> (FoxBerry's own BCs on the bed) is BLOCKED on a solver convergence defect found while setting
> this up.** See "Open issue" below — it caps or diverges the pressure solve, and a capped run is
> invalid, not merely slow. Do not report `packed` timings until it is fixed.

**First measured point (2026-09-01, genoa, 192 ranks = 1 full node, single-phase, 400³):**
**21.8 s/step against FoxBerry's 42.2 — 1.9× faster**, at 155.5 pressure iterations/step and a
final `max|div(open·u)|` of 7.2e-09 (converged, not capped). The projection is 85 % of the step
(18.6 s of 21.8), so the iteration count is where any further win lives — and it is high precisely
because of the 400³ factorization discussed below, which is why 384³ is now the default grid.

## Deliberate deviations from FoxBerry

All are recorded in every result JSON.

- **384³ = 56.6M cells (default), not 401³ = 64.5M.** peclet's geometric multigrid coarsens an
  axis only while it stays even, so an **odd dimension never coarsens at all** (measured
  elsewhere: 3.2× the step time at 384×128×255 vs …×256). 401³ would cripple the pressure solve
  for reasons that have nothing to do with parallel scaling. Among the even neighbours the
  *factorization* then decides everything: 384 = 2⁷·3 gives seven halvings and divides the whole
  rank ladder cleanly, where 400 = 2⁴·25 gives four. Measured at np=24 with 7 levels requested:

  | grid | aligned-ORB imbalance | coarse-first imbalance | MG levels achieved |
  |---|---|---|---|
  | 384³ | **1.000** | **1.000** | **7** |
  | 400³ | 1.422 | 1.030 | 5 / 4 |

  384³ is 12 % fewer cells than FoxBerry's 64.5M and `dx = 1/384` makes the spheres 21.35 cells
  across instead of 22.09 (−3.4 %) — a smaller problem, not a different one, and the difference is
  stated on the plot. A **400³ series** (`--export=ALL,GN=400`) is kept alongside it as the
  cell-count-matched reference; the gap between the two curves *is* the price of grid
  factorization, which is worth having measured rather than argued about.
- **The bed is `peclet.dem`-grown, not FoxBerry's generator.** Same N = 5000, same holdup 0.45,
  same radius from FoxBerry's own formula (r = 0.0276138 over their region; 0.0278004 for the
  triply-periodic variant over the full box). FoxBerry's seeded PRNG sequence is not reproducible
  outside FoxBerry, so the beds are statistically equivalent rather than identical — irrelevant
  for a timing comparison.
- **Initial velocity 0**, where FoxBerry starts at the inlet velocity (`flow` has no velocity
  setter). Immaterial for per-step timing; two warmup steps precede every measurement.
- **Solver tolerances are peclet production settings**, not FoxBerry's 1e-14: MG-PCG at
  rtol 1e-8 with a 200-iteration cap, momentum RB-GS with a 1e-3 tolerance stop. Recorded in the
  JSON; `PRTOL`/`PMAXIT`/`VRTOL` override.
- **Timing convention matches FoxBerry's graph**: wall time of `NSTEPS` steps after `WARMUP`
  steps, divided by `NSTEPS`, max-reduced across ranks.

## Files

| file | what |
|---|---|
| `make_bed.py` | grows the 5000-sphere beds with `peclet.dem` — the FoxBerry bed by default, the triply-periodic one with `PERIODIC=1`. Both npz files are committed as the reproducibility record. |
| `foxberry_bench.py` | the benchmark driver (both cases), one JSON per run |
| `plot_foxberry.py` | FoxBerry-style loglog plots with their reference curve overlaid, plus a comparison table |
| `snellius/foxberry_genoa.sh` | CPU strong scaling, genoa (192 cores/node), the 24…1536 ladder |
| `snellius/foxberry_gpu.sh` | the same cases on gpu_h100, 1…16 GPUs |

## Running it

The bed is committed, so nothing needs `dem` unless it is being regenerated:

```bash
source ~/Codes/suite/.venv/bin/activate
DEM_BUILD=~/Codes/suite/dem/build            python make_bed.py   # FoxBerry bed
DEM_BUILD=~/Codes/suite/dem/build PERIODIC=1 python make_bed.py   # triply-periodic bed
```

Local smoke test (small grid, an OpenMP `PECLET_FLOW_MPI=ON` build):

```bash
PYTHONPATH=~/Codes/suite/flow/build_mpi \
  CASE=packed BCMODE=periodic GN=96 NSTEPS=2 WARMUP=1 \
  PACK=results/packing_foxberry_periodic_n5000_phi0.45_s0.npz \
  OMP_NUM_THREADS=8 OMP_PROC_BIND=false python foxberry_bench.py
```

On Snellius — **submit from inside `snellius/`** (the scripts resolve `../foxberry_bench.py`,
`../results/…` and the shared `snellius_env.sh` relative to `SLURM_SUBMIT_DIR`). One job per rung,
queue-parallel safe, and **resumable**: finished JSONs are skipped, so a timeout is fixed by
resubmitting the same line. After any solver change pass a tag as argument 2, or the stale JSONs
are silently reported as the new numbers.

The **config list is argument 3**, not an env var — `CASES=single sbatch …` is silently dropped by
SURF's sbatch and runs the default. Measured the hard way on 2026-09-01.

`--mem=0` is in the script and matters: **`--exclusive` alone does not give you the node's
memory.** SLURM still caps the job at ~1792 MiB × ntasks, so a 24-rank job gets ~43 GB of genoa's
336 GB and is OOM-killed at this problem size (job 26280702, "Detected 2 oom_kill events"). Only
the ≤96-rank single-node rungs are exposed — at 192 ranks/node the per-task allowance already sums
to the whole node.

```bash
cd <peclet-examples>/benchmarks/foxberry-scaling/snellius
# arg1 = ranks, arg2 = result tag ("" for none), arg3 = config list
sbatch --nodes=1 --time=03:00:00 --mem=0 --export=ALL,NSTEPS=20 foxberry_genoa.sh 24 "" "single packed-periodic"
sbatch --nodes=1 --time=03:00:00 --mem=0 --export=ALL,NSTEPS=20 foxberry_genoa.sh 48 "" "single packed-periodic"
sbatch --nodes=1 --time=02:00:00 --mem=0 --export=ALL,NSTEPS=50 foxberry_genoa.sh 96 "" "single packed-periodic"
sbatch --nodes=1 foxberry_genoa.sh 192  "" "single packed-periodic"
sbatch --nodes=2 foxberry_genoa.sh 384  "" "single packed-periodic"
sbatch --nodes=4 foxberry_genoa.sh 768  "" "single packed-periodic"
sbatch --nodes=8 foxberry_genoa.sh 1536 "" "single packed-periodic"
sbatch --nodes=1 foxberry_gpu.sh 4 "" "single packed-periodic"          # H100 comparison
sbatch --nodes=1 --mem=0 --export=ALL,GN=400 foxberry_genoa.sh 192      # the 400^3 series
```

Do not add `packed` to the config list until the open issue below is resolved.

**Shorten the measured window at the low rungs.** The default is 100 steps, but 24 ranks costs
roughly eight times the 192-rank step time (~175 s/step), so 100 steps would need ~5 h and blow
the 2 h walltime — and charge ~960 core-hours for one point, since `--exclusive` holds all 192
cores either way. The per-step cost is stationary (pressure iterations sat at 153–161 across steps
10–80 at np=192), so 20 steps is a cheaper draw of the same number, not a different measurement.
`NSTEPS` must go through `--export=ALL,NSTEPS=…`, and the value used is recorded in each JSON.

**Read the low rungs with care.** genoa nodes are 192 cores and the jobs are `--exclusive`, so a
24-rank run has one whole node — eight times the memory bandwidth per rank of the 192-rank run on
that same node. An incompressible solve at 64M cells is bandwidth-bound, so 24/48/96 are
*flattered* relative to 192, and the ladder's apparent efficiency drop from 24 → 192 is partly
this, not parallel overhead. The **apples-to-apples segment is 192 → 1536** (1, 2, 4, 8 full
nodes, identical per-core resources throughout). FoxBerry's published curve is very close to ideal
halving across its whole ladder, which suggests their rungs kept per-core resources constant too —
so compare the *shape* on the full-node segment, and treat any peclet/FoxBerry ratio at 24–96 as
an upper bound on peclet rather than a measurement.

Pre-flight any (grid, np) combination without a GPU — but note this is slow above ~a hundred
ranks, so run it in the background:

```bash
PYTHONPATH=<build> python ~/Codes/suite/flow/scripts/check_decomposition.py \
  --grid 400,400,400 --levels 5 --np 24 --mode 0,coarse
```

Measured on 400³ (the check itself gets slow and sometimes times out above ~a hundred ranks):

| np | aligned ORB imbalance | coarse-first imbalance | coarse-first depth |
|---|---|---|---|
| 24 | 1.422 | **1.030** | 4 |
| 48 | 1.531 | **1.030** | 3 |
| 96 | 1.701 | (timed out) | — |
| 192 | (failed) | **1.030** | 3 |
| 384 | 2.222 | (failed) | — |

The driver therefore requests `DECOMP_LEVELS=5` (coarse-first) by default — at these rank counts
imbalance matters more than the extra level.

**Expect the high-rank end of the ladder to be unflattering to peclet, for a structural reason
worth stating in any writeup.** 400 = 2⁴·25, so the grid is poorly factored: aligned-ORB imbalance
reaches 2.2 by np=384, and at np=1536 each rank holds only 400³/1536 ≈ 34³ cells, at which point
the per-rank block — not the global grid — caps the multigrid depth, since a level coarsens an
axis only if *every* rank's block is even on it. FoxBerry's AMG has no such constraint. If the
comparison is to be about parallel efficiency rather than about grid factorization, rerun at
**384³ = 56.6M cells** (2⁷·3, seven halvings, divides the whole rank ladder cleanly) and say so;
that is a 12 % smaller problem, not a different one.

Collect and plot back on the workstation:

```bash
scp -r 'snellius:<...>/foxberry-scaling/snellius/results/*' results/
python plot_foxberry.py          # -> scaling_single.png, scaling_packed.png + table
```

Commit the JSONs; the logs are not committed.

## The packed configs need the fp64 operator build

**Any packed-bed config at 384³ must run against a `-DPECLET_FLOW_MREAL_DOUBLE` build**
(`sbatch --export=ALL,DOUBLE=1 build_fb.sh cpu` -> `fb/flow/build_omp_mpi_d`, selected at run time
with `--export=ALL,BUILD=...build_omp_mpi_d`). This is not a preference: with the default float
build the run is invalid.

The bed at 384³ (R = 10.7 cells, phi = 0.45) crosses the coefficient-contrast threshold of flow's
documented **WO-M** defect — float operator storage breaks the singular row-sum identity `A·1 = 0`
at ~eps_f32 per row, so the MG-PCG residual floors at 5e-9…6e-8 and then rebounds, and the solve
burns its iteration cap without ever meeting an rtol of 1e-8. Measured on this bed:

| build / driver / tolerance | pressure iters | `max｜div｜` | `<u>` | s/step |
|---|---|---|---|---|
| float, PCG rtol 1e-8 | **300 = CAP** | 2.314e-10 | 1.803374e-04 | 280+ (np=1, 16 thr) |
| float, PCG rtol 1e-6 | **36.5** | 2.313e-10 | 1.803374e-04 | 60.2 (np=1, 16 thr) |
| float, Chebyshev | 252.5 | 2.314e-10 | 1.803374e-04 | 243 (np=1, 16 thr) |
| float, FCG rtol 1e-8 | 300 = CAP | 2.314e-10 | 1.803374e-04 | 291 (np=1, 16 thr) |
| float, PCG, advection OFF | 300 = CAP | 2.314e-10 | 1.803375e-04 | 306 (np=1, 16 thr) |
| **fp64, PCG rtol 1e-8** | **71.0** | **1.086e-12** | — | **10.9 (np=192)** |

The tell is that `<u>` and `max|div|` are *identical to seven digits* across every float row: the
solve reaches its physical answer in ~36 iterations and spends the remaining ~264 chasing a
residual below the storage floor. The fp64 build is not merely more correct — it is **~2× faster
in wall clock** (71 iterations rather than a 200 cap) and lands two orders lower in divergence,
which is why it is the configuration to report. Chebyshev does converge in float, as flow's docs
predict for the contrast problem, but at 3.5× the iterations of fp64: usable, not preferable.

The onset is sharp in resolution and nothing else. The same bed converges in **11 iterations at
128³** and **20 at 256³** in float, and only caps at 384³. It reproduces at **np = 1**, so MPI is
not involved (np=1 and np=4 at 256³ agree to every digit). A 100× `dt` sweep at 128³ moves
iterations 9.5 -> 11; the bottom solver is irrelevant (`auto` vs `smoother`, coarsest 4³ vs 8³ —
all 20.0); and turning advection off changes nothing (still capped, same answer).

**The single-phase configs are low-contrast and converge fine in float** (16–39 iterations), so the
single ladder does not need the fp64 build and its numbers stand as published.

## Open issue — np = 768 stalls on 384³

Reproducible; recorded rather than diagnosed. The single-phase config at **np = 768 (4 genoa
nodes) hangs in warmup** — two independent allocations each sat >18 minutes without finishing two
warmup steps, at full CPU on every rank (which proves nothing either way: OpenMPI busy-polls a
blocked collective). The neighbouring rungs are healthy on the same build and grid — np = 384 does
2.48 s/step, np = 1536 does 0.85 s/step — so this is specific to 768, not a scaling wall. Its
per-rank block is a uniform 48×48×32 at imbalance 1.000. The 400³ np = 1536 job showed the same
symptom, and there the decomposition is visibly pathological (**imbalance 4.000**). When someone
picks this up: rerun with `PECLET_FLOW_AGGLOM_EXTENT=1000000` to take the agglomerated coarse
solve out of the picture, which would separate a coarse-solve collective from a halo one. The
ladder is reported without np = 768.

## Open issue — cut-cell IBM + open boundaries stalls the pressure solve

**Found 2026-09-01 while setting this benchmark up. This blocks the `packed` case and is a
genuine solver defect, not a tuning problem.** It needs to be addressed before the packed-bed
comparison means anything.

The FoxBerry packed-bed configuration is *cut-cell IBM together with inflow/outflow domain
boundaries* — a combination that, as far as the test matrix goes, **nothing in `flow` covers**:
no `tests/kokkos_mpi` test calls `setDomainBc` and `setSolid` together, and none of the
`verify_*_sdflow.py` domain-BC scripts carries an immersed solid. The porous studies are all
periodic; the BC studies are all all-fluid.

Measured on the committed bed at 100³, μ=1, dt=1, MG depth 3, MG-PCG rtol 1e-8 (cap 200):

| configuration | pressure iters/step | final `max｜div(open·u)｜` |
|---|---|---|
| all-fluid + inlet/outlet/4 walls (`CASE=single`) | 27.5 | 7.4e-09 |
| packed bed + **periodic** (`BCMODE=periodic`) | 15.0 | 2.9e-10 |
| packed bed + **6 no-slip walls** (`BCMODE=walls`) | 17.0 | 2.0e-09 |
| **packed bed + inlet/outlet/4 walls (FoxBerry)** | **200 = CAP** | **2.5e-03** |

Each ingredient alone is healthy. Only the combination fails, and it fails by six orders of
magnitude in the divergence residual — the projection is simply not being solved.

Depth and bottom-solver dependence (same case, cap raised to 300):

- `MGLEVELS=3, BOTTOM=smoother` — still caps at 300. **Not the agglomerated bottom.**
- `MGLEVELS=2` — **diverges**: `<u>` = NaN, `max|div|` = inf, and the driver reports *0*
  iterations (it breaks down immediately rather than iterating).
- `MGLEVELS=1` — **diverges**: `max|div|` = 1.8e+268, again 0 iterations.
- `PRESSURE=cheby` at depth 3 — **diverges** to NaN (0.5 iters/step).
- `PRESSURE=fcg` at depth 3 — caps at 200, like PCG.

So the shallow hierarchy blows up outright and the deeper one merely stalls; no choice of outer
Krylov driver survives, and the agglomerated bottom is exonerated.

**Where to look.** `flow/CLAUDE.md` documents that open boundaries split the face openness into
two roles — the *operator* openness α (0 at walls/inflow for Neumann, open at outflow for the
Dirichlet p=0 ghost) and the *flux* openness β (open at inflow and outflow so their flux is
counted). The walls-only ablation passing while inflow/outflow fails points at the **Dirichlet
(outflow) half** of that split meeting the cut-cell aperture rediscretization: `CutcellMG`
re-imposes boundary face openness on every coarse level and `applyOutflowGhost` holds the
outflow ghost at 0, but the coarse-level *cut-cell* openness at an open face is exactly the
place where a rediscretized aperture and a Dirichlet ghost have to agree. That the mean-removal
is switched off on the outflow path (the operator is non-singular there) makes an inconsistent
coarse operator fatal rather than merely inaccurate. WO-H fixed the Neumann counterpart
(`applyNeumannGhost`) for the all-fluid case in 2026-08-30; this looks like the cut-cell-side
sibling of that class of bug.

**Suggested next steps** (each cheap, none run yet):
1. Bisect the BC set: outflow-only (+5 periodic), inflow-only, then inflow+outflow, to confirm
   the outflow face is the trigger.
2. Move the bed away from the open faces (it currently starts 4 cells from the inlet, FoxBerry's
   rule) and see whether the stall tracks *cut cells near an open boundary* specifically.
3. Read out the preconditioner symmetry directly with `PECLET_FLOW_MG_DEBUG=2` (`pr` ≈ 0 iff M is
   symmetric w.r.t. the fine operator) and compare the four rows of the table above — the
   WO-H instrument, reused.
4. `PECLET_FLOW_MG_BCGHOST=0` as the ablation that restores the pre-WO-H ghost, to check whether
   the new Neumann ghost interacts with cut cells at an open face.
5. Once understood, the gate belongs in `tests/kokkos_mpi` as the first test that combines
   `setDomainBc` with `setSolid`.

The ablation knobs used above are kept in the driver (`BCMODE=foxberry|walls|periodic`) precisely
so this table can be regenerated after a fix.
