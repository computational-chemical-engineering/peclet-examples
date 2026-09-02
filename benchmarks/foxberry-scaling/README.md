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

## Results (Snellius genoa, 2026-09-02 — second campaign, telescoped multigrid)

384³ = 56.6M cells, pure MPI (one rank per core), 192 cores/node. `single` uses the default float
build; `packed` (FoxBerry's BCs: inlet, outlet, four walls, wall-confined bed) uses the fp64
operator build (see below — the float build is invalid there). Both with coarse-level telescoping
(`TELESCOPE=1`), 100 steps (20 / 25 / 50 on the one-node rungs). Seconds per step; bracket =
speedup over FoxBerry; `eff` = strong-scaling efficiency against the 24-rank rung.

| ranks | FoxBerry single | **peclet single** | iters | eff | FoxBerry packed | **peclet packed** | iters | eff |
|---|---|---|---|---|---|---|---|---|
| 24 | 327 | **34.8** (9.4×) | 14.7 | 100 % | 385 | **129** (3.0×) | 43.1 | 100 % |
| 48 | 166 | **18.3** (9.1×) | 14.8 | 95 % | 184 | **64.9** (2.8×) | 42.9 | 99 % |
| 96 | 84.3 | **8.56** (9.9×) | 14.4 | 102 % | 98.3 | **31.6** (3.1×) | 41.7 | 102 % |
| 192 | 42.2 | **4.29** (9.8×) | 14.0 | 101 % | 48 | **15.6** (3.1×) | 39.8 | 103 % |
| 384 | 21.1 | **2.01** (10.5×) | 14.0 | 108 % | 24.2 | **7.28** (3.3×) | 39.8 | 110 % |
| 768 | 10.6 | **0.768** (13.8×) | 14.0 | 142 % | 12 | **3.24** (3.7×) | 39.8 | 124 % |
| 1536 | 5.08 | **0.656** (7.7×) | 14.0 | 83 % | 5.44 | **1.33** (4.1×) | 39.8 | 151 % |

**Third pass — the momentum fix** (`VRES=1e-5`, residual-based stop; `VMG=3` = velocity multigrid,
else RB-GS), same telescoped pressure MG, same beds, pressure iterations and `<u>`/`max|div|`
unchanged to seven digits:

| ranks | FoxBerry single | **single, VMG** | FoxBerry packed | **packed, VMG** | **packed, RB-GS + residual stop** |
|---|---|---|---|---|---|
| 384 | 21.1 | **0.930** (22.7×) | 24.2 | **3.32** (7.3×) | **2.91** (8.3×) |
| 768 | 10.6 | **0.430** (24.6×) | 12 | **1.48** (8.1×) | — |
| 1536 | 5.08 | **0.391** (13.0×) | 5.44 | **0.834** (6.5×) | **0.844** (6.4×) |

The **shipped defaults** couple the momentum tolerance to the pressure solver's rtol (1e-8 here;
`set_velocity_residual_tolerance` overrides, 0 = legacy update criterion) and pick the velocity MG
by the auto rule: a run with no `VRES` / `VMG` / `TELESCOPE` flags measures 3.31 s packed at 384
(RB-GS, 16 sweeps/component), 0.898 s packed (3 V-cycles/component) and 0.368 s single-phase at
1536 — 7.3× / 6.1× / 13.8× FoxBerry, same seven-digit `<u>` / `max|div|`. (At the earlier fixed
1e-5 the same runs read 3.06 / 0.786 / 0.256 s, a mix of the looser tolerance and node placement.) Node placement moves
a 1536-rank step by up to 1.5× between allocations (0.391 vs 0.256 s for the identical single-phase
configuration), so top-rung A/Bs need a same-allocation control — the Chebyshev pressure driver,
measured that way, is parity single-phase (0.251 vs 0.256 s) and 5× slower on the bed (238 vs 40
iterations); its JSONs are in `rejected.txt` as experiments. The velocity MG runs one V-cycle per
component per step on the single-phase case (residual 5e-16 —
plug flow is trivial for it) and two on the bed; RB-GS with the residual stop needs 8.8 sweeps per
component instead of the cap of 200. The two momentum solvers tie at 384 and the V-cycle wins by its
fewer halo exchanges at 1536. At `VRES=1e-3` the momentum residual (8e-4) leaks into the pressure
solve (14 → 30 iterations single-phase), so 1e-5 is the setting to use.

Every run converged on every step (max 18 iterations single, 45 packed, cap 200); the 100-step
packed runs at 192 / 384 / 768 / 1536 agree on `<u>` and `max|div|` to seven digits, which is the
evidence that their halo topologies were clean (the hang section explains why that matters). **The pressure iteration count is now flat across the ladder**, so the
first campaign's whole strong-scaling deficit (16.6 → 38.7 iterations, 67 % at 1536) is gone; the
super-linear efficiencies are the shrinking per-rank block fitting cache, on top of a baseline that
one node's memory bandwidth flatters.

The A/B against the in-place hierarchy (`TELESCOPE` off), same build and bed: at 384 ranks the
packed bed needs 49.9 iterations (max 69) and 10.8 s/step in place vs 39.8 (45) and 7.28 s
telescoped; single-phase 24.9 / 2.48 s vs 14.0 / 2.01 s. At 24 ranks the two are identical
(129.5 vs 128.7 s) because the hierarchy already reaches full depth there. Measured ladders:
24 → 1 rank at 12³; 384 and 768 → 8 → 1; 1536 → 64 → 1 (predicted), all bottoming at 3³.

**The 1536 rung** hung on every attempt (and 768 intermittently) until the cause was found on
2026-09-02: a tag race between consecutive NBX consensus rounds in `core`'s topology builder,
transport-independent, more likely the larger the communicator (the hang section below). The 768
and 1536 rows are from the fixed engine (`tel4`); the earlier 768 point from the `-O2 -g`
diagnosis build (3.34 s, same numbers to seven digits) is superseded. At 1536 the two cases part
ways: the packed step is momentum-sweep-bound (600 sweeps/step, compute) and keeps gaining from
cache (151 %), the single-phase step (204 sweeps) is down to 37 k cells/rank and latency-bound
(768 → 1536 buys 1.17×).

### First campaign (2026-09-01, in-place multigrid, periodic stand-in bed) — superseded

Kept for the record and for the gray series on the packed graph. Single-phase: 36.5 / 19.1 /
8.95 / 5.30 / 2.48 / — / 0.852 s at 24 … 1536 with iterations 16.6 → 38.7; packed-periodic
(fp64): 67.9 / 33.8 / 17.7 / 10.3 / 6.19 s to 384 with iterations 52 → 82, then **invalid at
1536** (122 mean iterations with steps at the cap, 17 s/step). The decomposition of that loss —
`42.9× speedup = 100.0× per-iteration / 2.33× iteration growth` — is what motivated telescoping;
the analysis is in [`suite/docs/DECOMPOSITION_AND_MULTIGRID.md`](../../../suite/docs/DECOMPOSITION_AND_MULTIGRID.md)
§2.8 and the design in `suite/docs/MG_TELESCOPING_PLAN.md`.

### Where the packed-bed time went — and the momentum fix

Until the third pass, the packed-bed step was dominated by the **momentum solve**: the implicit
diffusion's Red–Black Gauss–Seidel hit its sweep cap every step (`momentum_sweeps_per_step` = 600 =
3 × `VSWEEPS` 200) because ν·Δt/Δx² ≈ 4×10⁴ here, versus 204 sweeps single-phase. The a-priori
study (`study/velocity_solver_residual.py`, 96³) showed the cap was buying nothing: the stop rule
"update ≤ rtol × the *first* sweep's update" is relative to a quantity that is already noise on a
warm-started near-steady step (the update-stopped run and one 25× longer agree to 1e-14). With the
residual-based stop (`set_velocity_residual_tolerance`, `VRES`): 468 → 24 sweeps/step at 96³ for
the same accuracy, and at scale the table above. The velocity multigrid (`VMG`), now running under
MPI with the mixed solid + domain-BC operator, converges to the same fixed point as RB-GS (2e-11)
in 1–2 cycles per component, and its depth is irrelevant on a pore-confined bed (2, 3, 5 levels
identical) — it needs no telescoping. Details and the two traps it cost (`bcStencilPath()` /
`implicitAdv()` must agree with the solver in use; level-0 ghosts are reflections, `fold=0`) are in
`suite/docs/SCALING_ISSUES.md` §5 and `flow/CLAUDE.md`.

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

The **second campaign** (the results table above) is the same ladder with telescoping on, the
`packed` config (FoxBerry BCs, wall-confined bed) on the fp64 build, and the halo timeout armed as
a safety net — a hang then aborts with a named culprit instead of burning the allocation:

```bash
D=$SUITE/fb/flow/build_omp_mpi_d
sbatch --nodes=1 --time=03:00:00 --mem=0 --export=ALL,TELESCOPE=1,NSTEPS=20,BUILD=$D foxberry_genoa.sh 24 tel packed
sbatch --nodes=2 --time=01:00:00 --mem=0 --export=ALL,TELESCOPE=1,BUILD=$D foxberry_genoa.sh 384 tel packed
sbatch --nodes=8 --time=01:00:00 --mem=0 --export=ALL,TELESCOPE=1,BUILD=$D,PECLET_CORE_HALO_TIMEOUT=300 foxberry_genoa.sh 1536 tel packed
sbatch --nodes=8 --time=01:00:00 --mem=0 --export=ALL,TELESCOPE=1 foxberry_genoa.sh 1536 tel single   # float build is fine single-phase
sbatch --nodes=2 --time=01:00:00 --mem=0 --export=ALL,BUILD=$D foxberry_genoa.sh 384 off packed       # the in-place A/B
```

`TELESCOPE=1` maps to `Solver.set_pressure_telescope(True)` and is recorded in the JSON
(`telescope`, plus the predicted `hierarchy` ladder); `plot_foxberry.py` keys the series on it.

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
2. **MG depth capped by the per-rank block** — the whole strong-scaling deficit. **Fixed** by
   coarse-level telescoping (2026-09-02), measured above.
3. **Solid intersecting an open domain face stalls the solve** — narrow, and *not* what it first
   looked like: the original "cut-cell IBM + open BCs is a blocker" finding was an artifact of a bed
   whose spheres were clipped at the inlet/outlet. With the correct bed, Case 3 runs.
4. **Intermittent multi-node hang in warmup** — **root-caused and fixed 2026-09-02**: an NBX
   inter-round tag race in `core`.
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

## Resolved — the intermittent hang in warmup at multi-node scale

**Cause.** `core`'s `NbxEngine` ran consecutive consensus rounds on one communicator with the
same tag. `GridHaloTopology::buildTopology` runs one round per multigrid level, back to back; a
rank that has observed round *k*'s `Ibarrier` complete posts round *k+1*'s `Issend`s while a
neighbour still draining round *k* probes `MPI_ANY_SOURCE` on that tag and takes the new message
as an old one. The recv side of a topology is computed locally, the send side is learned from the
round — so the victim never learns it must send, and the first exchange on that level waits
forever. Larger communicators, larger barrier-completion skew, more likely: hence ≥ 4 nodes and
intermittent. Fixed in core `10294e6` (per-communicator round counter rotates the tag; the
builder now cross-checks promised vs requested cells and throws on a mismatch).

**How it was found**, for the next one like it:

1. `snellius/stack_census.sh <jobid> <node-index…>` — parallel `gdb -p` over all 192 ranks of a
   node in ~2 minutes, tallying the innermost solver frame and the MPI call. On the hung 1536-rank
   telescoped job: 178 ranks in the telescope `Scatterv`, the 8 group roots in
   `GridHalo::exchangeEnd` — so the hang was the *first* exchange on the 64-rank sub-hierarchy's
   freshly built topology, which already pointed at the builder rather than the transport.
2. `PECLET_CORE_HALO_TIMEOUT=180` (with `--export=ALL,…`) on a `RelWithDebInfo` build
   (`build_fb_dbg.sh`): every `exchangeEnd` becomes a deadline wait that prints the pending
   requests — direction, partner in the exchange's communicator *and* in `MPI_COMM_WORLD`, byte
   count, the level label — and aborts. The report: level 5 on 64 ranks, 26 recv partners on
   every rank, send partners 26 / 24 / 16 / 12 / 10 / 8 / 6 / 0, every pending request a RECV.
3. The acceptance test that would catch the silent face of it (a leaked message matched by a
   later tag-0 receive gives wrong ghost values without a hang): every 100-step rung must agree
   with the other rank counts on `<u>` and `max|div|` to seven digits (1.002348e-03 / 3.514e-06
   at 8 levels + 5 warm-up steps). A 768-rank run that read 1.002349e-03 / 3.403e-06 looked like
   that and was not — it had run with 7 levels and 2 warm-up steps, and a clean 1536-rank run with
   the same settings reproduced it exactly. Settings drift between submissions is the more likely
   explanation of a seventh-digit difference; check `mglevels` / `warmup` in the JSON first.

Earlier hypotheses recorded here (UCX transport, `ob1`, rank density, the agglomerated bottom's
`Allgatherv`) were all wrong and are retracted; the discriminators that were run (`ob1`, 16 × 96)
were consistent with the real cause, which is transport-independent.

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
