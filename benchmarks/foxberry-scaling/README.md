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
| **packed** | Case 3, packed-bed IBM | same box/BCs, inlet u=0.001, 5000 spheres at holdup 0.45, cut-cell IBM, on the **wall-confined** bed |
| **packed-periodic** | (no FoxBerry counterpart) | the same bed and cell count, but **fully periodic and body-force driven**, on a triply-periodic bed — a clean periodic reference |

`packed` is the faithful reproduction. `packed-periodic` is *not* — the boundary conditions differ.
It is the same problem *size* (same cells, same 5000 spheres, same holdup, same sphere radius to
0.7 %); it was introduced when `packed` was believed blocked, and is retained as a periodic
reference. The plot labels it as such.

**The beds are different artifacts and are not interchangeable**, so `make_bed.py` produces each by
name (`BED=walls|periodic`) and `foxberry_bench.py` **refuses** a mismatched pairing:

- **`BED=walls` (default, the faithful one).** FoxBerry's `ObjectCoordinateGenerator` places centers
  uniformly in a box inset by `radius + clearance` on every non-periodic axis, then pushes overlaps
  apart within those bounds (verified in `ObjectCoordinateGenerator.cpp`, lines 182–189) — so its
  bed is **wall-confined in all three directions**, whole spheres inside
  [0.01, 0.99] × [0, 1] × [0, 1], nothing clipped. Reproduced here by growing the packing against
  six `dem` planes on the region boundary: measured protrusion 1e-6 R, zero overlap, physical x-span
  0.01 … 0.98997, and a sampled domain solid fraction of **exactly 0.4410 = 0.45 × 0.98**.
- **`BED=periodic`.** Triply periodic over the full unit box (r = 0.0278004), for `packed-periodic`.

*An earlier version of this benchmark used a y/z-periodic bed whose spheres were clipped at the
inlet and outlet. That is not what FoxBerry does, and it produced a false "cut-cell IBM + open BCs
is broken" finding — with the correct bed, Case 3 runs. The legacy bed is kept only as the
reproducer for the narrower defect it did expose (see the open issue below).*

> **Status: all three configurations run.** `packed` needs the fp64 operator build like any dense
> bed (see below). The narrower open-face defect that the legacy bed exposed is still open, but it
> does not affect these runs.

## Results (Snellius genoa, 2026-09-01)

384³ = 56.6M cells, pure MPI (one rank per core), 192 cores/node. `single` uses the default float
build; `packed-periodic` uses the fp64 operator build (see below — the float build is invalid there).

| ranks | FoxBerry single | **peclet single** | iters | FoxBerry packed | **peclet packed-per.** | iters |
|---|---|---|---|---|---|---|
| 24 | 327 | **36.5** (9.0×) | 16.6 | 385 | **67.9** (5.7×) | 52.4 |
| 48 | 166 | **19.1** (8.7×) | 16.6 | 184 | **33.8** (5.4×) | 52.2 |
| 96 | 84.3 | **8.95** (9.4×) | 16.5 | 98.3 | **17.7** (5.5×) | 61.6 |
| 192 | 42.2 | **5.30** (8.0×) | 22.7 | 48 | **10.3** (4.7×) | 65.5 |
| 384 | 21.1 | **2.48** (8.5×) | 24.9 | 24.2 | **6.19** (3.9×) | 81.7 |
| 768 | 10.6 |  — (hung, see below) | — | 12 | — | — |
| 1536 | 5.08 | **0.852** (6.0×) | 38.7 | 5.44 | *invalid — caps* | 122† |

Seconds per step; the bracket is peclet's speedup over FoxBerry. Every run converged
(`max|div(open·u)|` 2e-10…2e-09 single-phase, 2e-13…9e-13 packed/fp64); capped runs are excluded by
`plot_foxberry.py` on principle, since a capped step time is set by `PMAXIT` rather than by
convergence.

**peclet is 8.0–9.4× faster than FoxBerry on the single-phase case and 3.9–5.7× on the packed bed**,
narrowing at the top of the ladder because FoxBerry scales better than peclet does.

† **The packed bed does not survive np=1536 even in fp64**, and that is a finding rather than a
gap. Both runs land on **122.2 mean iterations with individual steps at the 200 cap**, and they agree to
every digit in `<u>` and `max|div|` — this is deterministic, not a flaky draw. The step time
*regresses* to 16.9 / 17.3 s against 6.19 s at np=384 — peclet goes from 3.9× faster than FoxBerry to slower. Meanwhile np=384
reproduces to 5 % across two runs (6.19 / 6.52 s, 81.7 iterations both times), so this is the rank
count and not the draw. The mechanism links the two top issues: the starved hierarchy (issue 3) weakens the
preconditioner enough to push the high-contrast bed back over the convergence threshold (issue 2).
**384 ranks is therefore the measured strong-scaling ceiling of the IBM path on this problem** — a
much lower one than the single-phase case's, and the reason fixing issue 3 is worth more than its
33 % headline suggests.

### Is the scaling linear?

Close to linear to 384 ranks, then not. Single-phase efficiency against the np=24 baseline:
100 % → 96 % → **102 %** → 86 % → 92 % → **67 %** at 1536. The packed bed behaves the same way
(100 → 100 → 96 → 83 → 69 %).

The loss decomposes exactly, and it is **not communication**:

```
speedup = (per-iteration speedup) / (iteration-count growth)
42.9x   =        100.0x           /         2.33x            (single-phase, 24 -> 1536)
```

Time *per pressure iteration* improves 100× over a 64× rank increase — **156 % efficiency,
super-linear**, because the shrinking block fits cache better. The entire wall-clock deficit is the
pressure solve needing 2.33× more iterations (16.6 → 38.7). That is the multigrid depth being capped
by the *per-rank block*: at np=1536 each block is 24×48×32, which stops coarsening at 3×6×4, so the
hierarchy is several levels shorter than the global grid would allow. The projection's share of the
step tracks it exactly, 39 % → 67 %.

**This is an implementation limit, not a property of multigrid, and it is now the top open item**
— coarse levels are required to be the fine decomposition coarsened *in place*, so the hierarchy
stops rather than redistributing onto fewer ranks. FoxBerry's MueLu repartitions its coarse levels
and consequently holds near-ideal halving across the whole ladder. Written up with the standard
remedies (PETSc `PCTELESCOPE`, MueLu `RepartitionFactory`, hypre's redundant coarse solve) in
[`suite/docs/DECOMPOSITION_AND_MULTIGRID.md`](../../../suite/docs/DECOMPOSITION_AND_MULTIGRID.md)
§2.8 and open problem 1.

Two caveats on reading the table. The 24/48/96 rungs sit on one `--exclusive` node, so they have up
to 8× the memory bandwidth per rank of the 192-rank run; that *flatters the baseline* and therefore
understates the efficiencies above. And 400³ shows the same mechanism amplified — iterations climb
96 → 191 between np=48 and np=384, efficiency falls to 63 % — so a 12 % difference in cell count
buys a 7.7× difference in iteration count at np=384. That is the price of grid factorization,
measured.

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

## Issues this campaign surfaced

Six, prioritized in **[`suite/docs/SCALING_ISSUES.md`](../../../suite/docs/SCALING_ISSUES.md)** —
read that first if you are picking any of them up. Ordered *silently wrong* before *visibly broken*
before *slow*:

1. **Float operator storage silently invalidates dense-bed runs** (the default build; fp64 is both
   correct and ~2× faster here).
2. **MG depth capped by the per-rank block** — the whole strong-scaling deficit.
3. **Solid intersecting an open domain face stalls the solve** — narrow, and *not* what it first
   looked like: the original "cut-cell IBM + open BCs is a blocker" finding was an artifact of a bed
   whose spheres were clipped at the inlet/outlet. With the correct bed, Case 3 runs.
4. **Intermittent multi-node hang in warmup** (cost two rungs of this ladder).
5. Velocity multigrid is single-rank only — impact here unverified, worth a `VSWEEPS` sweep.
6. `check_decomposition.py` too slow to pre-flight the high rungs.

The sections below are the detail for 1, 4 and 3 respectively.

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

## Open issue — intermittent hang in warmup at multi-node scale

Reproducible in aggregate, intermittent per job; recorded rather than diagnosed, and the reason two
cells of the results table are empty.

Some multi-node runs hang in the **first warmup step** and never emit another line, at full CPU on
every rank — which distinguishes nothing by itself, since OpenMPI busy-polls a blocked collective.
Observed:

| run | nodes | outcome |
|---|---|---|
| single 384³ np=768 | 4 | hung, **twice**, in two independent allocations (>18 min each) |
| single 400³ np=1536 | 8 | hung (>75 min); its decomposition is also pathological, **imbalance 4.000** |
| packed-periodic 384³ np=1536 | 8 | hung (>44 min) — **but an earlier attempt cleared warmup in 28 s** |

That last row is the informative one: the same configuration both hung and ran, so this is not a
deterministic function of rank count, and np=768 is not special — it is an intermittent failure that
happens to have hit np=768 twice. Healthy neighbours on the same build and grid (np=384 at 2.48
s/step, np=1536 single at 0.852 s/step) rule out a scaling wall.

When someone picks this up, the cheap discriminators are: rerun with
`PECLET_FLOW_AGGLOM_EXTENT=1000000` to take the agglomerated coarse solve (a global `Allgatherv`
inside every V-cycle) out of the picture, which separates a coarse-solve collective from a halo
one; and `PECLET_CORE_GPU_AWARE_MPI=0` / the host-staged halo path to isolate the exchange engine.
A stack dump from one hung rank (`gdb -p` on the compute node) would settle it in one shot and is
worth more than any amount of black-box bisection.

## Open issue — solid intersecting an OPEN domain face stalls the pressure solve

**Corrected 2026-09-01, the same day it was found.** This was first written up as "cut-cell IBM +
inflow/outflow BCs does not solve", and reported as the blocker for FoxBerry's Case 3. That was
**wrong**. The bed used to find it had spheres *clipped by the inlet and outlet planes* — an
artifact of how that bed was built, not a property of the configuration. With FoxBerry's actual
placement (whole spheres, clear of the open faces) the identical configuration converges, and
Case 3 is reproducible.

The real defect is the narrower one: **solid that *cuts* an open (inflow/outflow) face** stalls the
cut-cell pressure solve. Measured A/B, everything identical at 128³ (μ=1, dt=0.78, `MGLEVELS=4`,
MG-PCG rtol 1e-8, cap 300) except the bed:

| bed | pressure iters | capped | final `max｜div(open·u)｜` |
|---|---|---|---|
| whole spheres inside [0.01, 0.99] (`BED=walls`) | **32.7** (max 37) | none | 9.6e-05 → **1.95e-06** over 42 steps |
| spheres clipped by the inlet/outlet (legacy bed) | 260.8 (max 300) | **5 of 6 steps** | 4.0e-03 |

The healthy row keeps improving — over 42 steps its divergence falls to 1.95e-06, its iteration
count settles at 29.2, and `<u>` tracks the inlet to 2 % (1.018e-3 against 1.0e-3).

The coarser earlier evidence still localizes *which* boundary is implicated, since it was all taken
on the clipped bed: that geometry is healthy under periodic BCs (15 iterations) and under six
no-slip walls (17), and an all-fluid domain is healthy under the open BCs (27) — so it is the
open-boundary treatment meeting solid *at that boundary*, not either alone. At `MGLEVELS` ≤ 2 the
clipped case diverges outright (NaN, 1e+268, 0 iterations); `BOTTOM=smoother` also caps, so the
agglomerated bottom is exonerated; FCG caps and Chebyshev NaNs.

It sits inside a wider gap: **nothing in `flow` combines solid with domain BCs at all** — no
`tests/kokkos_mpi` test calls `setDomainBc` with `setSolid`, and no `verify_*_sdflow.py` domain-BC
script carries an immersed solid. Suspected mechanism (how a cut cell on an open face reconciles the
operator openness α, Dirichlet with mean-removal off, against the flux openness β), a
minimal-reproducer plan, and the option of *rejecting* the configuration outright rather than fixing
it: [`flow/doc/cutcell_openbc_convergence.md`](../../../suite/flow/doc/cutcell_openbc_convergence.md).

Reproduce the A/B:

```bash
for bed in walls n; do
  case $bed in
    walls) P=results/packing_foxberry_walls_n5000_phi0.45_s0.npz ;;
    n)     P=results/packing_foxberry_n5000_phi0.45_s0.npz ;;
  esac
  PYTHONPATH=~/Codes/suite/flow/build_mpi PACK=$P CASE=packed BCMODE=foxberry \
    GN=128 NSTEPS=6 WARMUP=2 MGLEVELS=4 PMAXIT=300 \
    OMP_NUM_THREADS=8 OMP_PROC_BIND=false python foxberry_bench.py 2>&1 |
    grep -E "^\[(sdf|perf|sanity)"
done
```

**The methodological lesson is worth more than the defect.** An A/B is only as good as its claim
that A and B differ in one thing. The bed was doing double duty — "the geometry" and "the thing that
touches the boundary" — and conflating those produced a confident, wrong, top-priority finding that
also declared a reproducible benchmark case unreproducible.
