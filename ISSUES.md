# Issues found while building examples

A running log of unexpected results, rough edges, and suspected bugs surfaced by
the example gallery — the channel through which examples feed improvements back
into the `peclet` suite. See [STYLE_GUIDE.md §8](STYLE_GUIDE.md): log it here
*before* working around it.

**Entry template**

```
## [short title]
- **Status:** open | investigating | filed (<link>) | resolved (<commit/PR>)
- **Package / area:** flow (pressure MG) | dem | voro | core | packaging | ...
- **Found in:** examples/<slug>  (or a scratch run)
- **Observed:** what happened (numbers, error text)
- **Expected:** what should have happened
- **Repro:** minimal steps / params
- **Notes:** hypotheses, workaround used (if any)
```

---

## Bidisperse bed did not fluidize — porous continuity silently disabled on a bare box
- **Status:** resolved (flow `0e19de4`, coupling `78353b3`)
- **Package / area:** flow (porous projection) + coupling (CfdDem driver)
- **Found in:** examples/bidisperse-segregation — the bed refused to fluidize at ANY gas
  velocity up to 4.5 m/s, while MFIX-Exa fluidizes and segregates it at 2.0 m/s.
- **Observed:** per-grain drag/weight ≈ 0.03–0.16 (~20–30× too weak); plane-flux probe: the
  volume-averaged continuity was **never enforced** — `flow`'s porous projection lives on the
  cut-cell pressure operator, and this example (a plain box, domain BCs only, no
  `set_solid`/`set_pressure_geometry`) had none, so `step()` ran with **no projection at all**.
  The gas never accelerated to the interstitial velocity `U/ε` in the bed → the slip the drag law
  saw was ~5× too small → Gidaspow drag far below grain weight. `max_porous_residual()` returned
  exactly 0 the whole time (it early-outs on the same flag), masking the failure. Every other
  porous example (`fluidized-bed`, `single-bubble-injection`) calls `set_solid`, which is why only
  this one failed. Two earlier suspects were ruled out en route: the ε=0.4 clamp (real, ~3× drag
  under-prediction, fixed separately — clip to [0,1] only + MFIX-style diffusive porosity
  smoothing `smooth_width`) and a CUDA/OpenMP discrepancy (a stale OpenMP build of flow predating
  the 07-09 superficial-velocity fix).
- **Expected:** imposed inlet velocity = superficial velocity; gas accelerates to `U/ε` inside the
  packing; Gidaspow drag then exceeds ceramic weight at 2.0 m/s (Ergun ΔP/weight ≈ 1.33).
- **Resolution:** flow `step()` now **throws** when porous continuity is on without the cut-cell
  operator (silent wrong physics → loud error), and `CfdDem` auto-installs an all-fluid
  `set_pressure_geometry` when missing. Validated: synthetic column carries flux = U exactly at
  every plane with in-bed w = U/ε; the bidisperse bed now sorts like the benchmark (nylon
  20→31 mm up, ceramic 20→16 mm down, +15 mm separation in 1.2 s); Ergun/terminal-velocity tests
  and the flow regression suite unchanged.

## Poiseuille example reported a fake "convergence" — misleading validation metric
- **Status:** diagnosed (root cause found); fix pending — see Notes
- **Package / area:** examples (poiseuille-ibm) + flow `scripts/verify_poiseuille_sdflow.py`
- **Found in:** examples/poiseuille-ibm — user challenged "a 2nd-order method must
  reproduce a quadratic exactly, so N=16 should have ~0 error."
- **Observed:** peak-velocity "error" 2.78% → 0.69% → 0.15% presented as O(h²)
  convergence of the cut-cell IBM.
- **Expected:** near-zero error at every resolution (Poiseuille is exactly
  quadratic; a 2nd-order scheme is exact on quadratics).
- **Diagnosis (confirmed):** the solver IS exact. Pointwise, the computed profile
  matches the analytic parabola *at the grid nodes* to ~6e-8 at N=16 (solver
  tolerance), on BOTH the staggered and collocated meshes (identical). The
  reported error was a **metric artifact**: `U_max` is the discrete max sampled at
  a node, but the half-integer walls put the channel centre on a half-integer —
  always 0.5h from the nearest node — while `U_ana = F H²/(8μ)` is the *continuum*
  peak. The gap is the parabola's drop over half a cell, `F/(2μ)(0.5h)² = 0.0125`,
  a CONSTANT independent of N; dividing by `U_ana ∝ H²` fabricates the shrinking
  percentage. Proof: keep cut cells but shift the peak onto a node (walls
  10.5/21.5, centre=16.0) → `U_max` matches `U_ana` to 0.000%. Also note the study
  "refines" at fixed h=1 (H grows 6→12→26), so it isn't spatial refinement anyway.
- **Fixes:**
  1. examples/poiseuille-ibm — validate pointwise against the parabola sampled at
     the same nodes (report max node error ~1e-7 at all N, both meshes); drop the
     fake log-log convergence plot. A genuine O(h²) convergence demo needs CURVED
     geometry (Zick–Homsy spheres), where boundary-representation error is the O(h²)
     term — make that a separate example.
  2. **flow (suite):** `scripts/verify_poiseuille_sdflow.py` uses the same lenient
     `U_max`-vs-continuum metric with a 2% tolerance — it PASSES for the wrong
     reason and would not catch a genuine first-order regression. Tighten it to
     assert the pointwise node error (~1e-6), which actually tests method order.

## Immersed solid + inflow/outflow is broken in three concrete ways (flow)
- **Status:** RESOLVED (flow `src/flow_ibm.hpp`) — the core blocker (c) is fixed; a
  no-slip immersed body in an inflow/outflow domain now runs stably. See "Resolution" below.
- **Package / area:** flow — an immersed SDF body (`set_solid`) together with
  inflow/outflow domain BCs (`set_domain_bc` type 2/3). The suite has never exercised
  this combination (immersed solids use periodic/body-force; inflow/outflow cases —
  channel, BFS — use `set_pressure_geometry` with NO immersed solid). This is the
  "inflow/outflow issue" to repair in `peclet.flow`.
- **Found in:** prototyping the cylinder-vortex-street example.

  **(a) `set_pressure_geometry()` after `set_solid()` SILENTLY WIPES THE SOLID.**
  Minimal repro (80 steps, flow past a cylinder, uniform inflow):
  - `set_solid(sdf, cutcell_pressure=False)` **then** `set_pressure_geometry(all-fluid)`
    → mean|u| *inside* the cylinder = **1.000** (no no-slip at all), max|u| = 1.000
    (uniform flow — the body has vanished).
  - `set_pressure_geometry(all-fluid)` **then** `set_solid(...)`, or `set_solid`
    alone → mean|u| inside = 0.62, max|u| = 2.05 (body present, flow accelerates).
  So the two geometry setters overwrite each other and the result is **order-
  dependent and silent**. A 6000-step cylinder run built the "solid then geometry"
  way produced a perfectly uniform field (no wake, no shedding) — 19 min wasted on a
  domain with no cylinder in it. Fix: make the setters compose (or error) instead of
  the last one silently clobbering the other.

  **(b) `cutcell_pressure=False` gives leaky no-slip.** Even with correct ordering,
  the velocity IBM leaves mean|u| ≈ 0.62 *inside* the solid (should be ~0), because the
  pressure operator treats the solid as fluid. Fine for the flat/periodic Poiseuille
  cases (x-independent), wrong for a bluff body.

  **(c) `cutcell_pressure=True` (proper no-slip) + inflow/outflow → NaN.** Elevated
  divergence (~1e-5 vs ~1e-8) growing to NaN over a few hundred steps at dt=0.3.
- **Resolution (root cause — different from the original hypothesis):** the *pressure*
  operator already composed domain-BC openness with the cut-cell operator correctly.
  The real bug was in the **momentum (velocity-diffusion) solve**: on the staggered grid,
  `smoothComp` short-circuited to a **constant-coefficient, all-fluid** diffusion smoother
  whenever domain BCs were active (`has_bc_`), *discarding the cut-cell IBM stencil
  entirely* (the code path was literally commented "domain-BC — no immersed solid"). So the
  velocity field never saw the body while the projection did → operator mismatch → energy
  injection → blow-up (it NaN'd even in Stokes/advection-off, proving it was not CFL). Fix:
  when a solid is actually present (`has_solid_`, any inner SDF < 0) *and* domain BCs are
  set, route the staggered momentum solve through the Robust-Scaled cut-cell IBM stencil
  with domain-BC ghosts refreshed each colour (reflection walls/inflow + zero-gradient
  outflow) — mirroring the already-correct collocated path. The all-fluid channel/BFS path
  is gated out (`has_solid_` false there) so it stays byte-identical.
- **Validated (OpenMP, single rank):** a confined D=16 cylinder at Re=40 (inflow/outflow,
  no-slip ±y walls) that previously NaN'd by step ~200 now runs stably to steady state —
  no-slip holds (mean|u| inside ≈ 2.5e-3), max|u| steady ≈ 1.78, divergence bounded
  (~1e-6–1e-4, decaying with the transient). Channel (`verify_channel`) is byte-identical.
  The BFS instability turned out to be a *separate*, still-open pre-existing issue (an
  advection-driven marginal mode at the profile inlet / outflow) — see the "Inflow/outflow
  diverges to NaN" entry below; not resolved here. GPU (CUDA/HIP) revalidation still
  recommended before shipping the compute-heavy wake example.
- **(a)/(b) status:** with (c) fixed, the single correct call for a no-slip immersed body
  in an inflow/outflow domain is `set_solid(sdf, cutcell_pressure=True)` — you do **not**
  call `set_pressure_geometry` as well (docstrings updated to say so). The setters still
  share one SDF, so calling both is still a footgun; a hard error/compose was left for
  later since the correct single-call path now works. (b) is by-design: `cutcell_pressure`
  must be `True` for a bluff body.
- **UPDATE (SHIPPED):** the `cylinder-vortex-street` example is now live on the
  Schäfer–Turek 2D-2 geometry (Re=100). Released in **peclet-flow 0.2.1** (→ peclet
  0.2.2): the momentum fix above + `set_backflow_stabilization` (vortices leave the
  outlet) + `set_deferred_correction` (higher-order advection — the coarse-grid
  numerical dissipation was suppressing shedding into a false steady wake; turning it
  on lets the Kármán instability grow). Even at a CPU-affordable D=10 it sheds cleanly:
  **St=0.267** (benchmark ~0.30; ~10% low from the under-resolved D≈1-cell boundary
  layer), Δp≈2.5 (matches). C_D/C_L still need a force-on-solid query flow doesn't
  expose. Finer D (GPU) converges St→0.30. Render is ~70 min at D=10 on CPU.
- **Consequence:** the cylinder-vortex-street example is now unblocked on the solver
  (still GPU-territory for resolution/runtime, per the note below).
- **The stable route (for when it's built on a GPU):** drive the cylinder in a fully
  **periodic** box with a body force (the Zick–Homsy path — immersed solid + periodic,
  no domain BCs), advection ON. This path is *stable* — a D=16 cylinder ran to Re≈134
  with no NaN (the inflow/outflow path NaNs by step ~200). Two remaining requirements
  make it GPU-territory: (i) a Re≈100 wake needs the cylinder resolved to D≳30 cells
  (boundary layer ~D/√Re), i.e. a large 2-D domain (~20–40 min/run on CPU); (ii) below
  that resolution the "steady" wake is a confinement/under-resolution artifact (a real
  cylinder sheds by Re≈47), so it must not be presented as a benchmark. Build it on the
  CUDA/HIP `peclet` build with D≈30–40 and a large periodic box, probe the wake for the
  shedding frequency, and report St vs the isolated-cylinder value with the array-spacing
  caveat. The classic *inflow/outflow* street additionally needs the solver fix above.

## Pore-scale (random packing) permeability converges slowly on CPU
- **Status:** documented (physical/practical, not a bug)
- **Package / area:** flow (cut-cell Stokes) — resolution demand for random packings
- **Found in:** examples/random-packed-bed
- **Observed:** Stokes solves through a random close packing hit the step cap without
  a tight steady-state and the permeability is resolution-sensitive at N≤64 (tight
  pore throats only a few cells wide); k ≈ 1.0e-3 vs Carman–Kozeny ≈ 6.3e-4.
- **Expected:** grid-converged k (as for the smooth Zick–Homsy lattice, which
  converges cleanly at these N).
- **Notes:** Not a solver bug — near-touching grains make the limiting throats
  under-resolved on CPU-affordable grids. The example is written honestly around this
  (characterisation + trend + caveat); grid-converged random-bed permeability needs
  the GPU build for finer grids. Continuation seeding (coarse→fine `set_state`) would
  also help the solve reach steady state in fewer steps.

## dem: periodic collisions across a boundary are NOT detected/resolved (SEVERE)
- **Status:** RESOLVED (dem 0.2.1, commit 46dbe71) — periodic ghost halo layers were not
  being filled in the CUDA→Kokkos port. The 2-particle boundary repro now detects the
  overlap (0.400) and resolves to touching (1.000), identical to the interior pair. The
  `random-packed-bed` example was regenerated against the fix: φ=0.629, Z=6.63, 0
  rattlers, min gap ≥ 0, g(r)=0 for r<d with the contact peak at d, and permeability
  ~6% above Carman–Kozeny (the corrected porosity ε=0.371 vs the earlier wrong 0.34).
  Two example-side fixes were also needed: use the EFFECTIVE radius
  `baseRadius*scale*growth_factor` (the growth factor < 1 at jamming; omitting it
  overstated radii and faked overlaps), and use the properly-annealed `pack.py`
  protocol at phi_ref≈0.63 (the earlier phi_ref=0.66 + crude feedback overshot jamming).
  Original report below.
- **~~Status~~:** ~~open~~ — CONFIRMED with a 2-particle minimal repro; corrupts every periodic packing
- **Package / area:** dem — single-GPU `step()` periodic ghost-contact resolution
- **Found in:** examples/random-packed-bed — user noticed the g(r) has weight at r < d
  (spheres closer than one diameter), i.e. overlap, which is impossible for hard spheres.
- **Observed:** a periodic sphere packing generated with the Lubachevsky–Stillinger
  protocol contains **deep real overlaps** (min pair gap ≈ −0.77 of a radius; centres
  0.23 apart for r=0.5 spheres; ~170/19900 pairs overlapping), yet dem's
  `get_max_overlap()`/`compute_overlaps()` report **0**. So the growth feedback (which
  keys off `compute_overlaps`) never backs off → grows to full scale → interpenetration;
  and the reported φ and coordination Z are inflated by the overlaps.
- **Root cause (minimal repro, box L=6, r=0.5, periodic):**
  - INTERIOR pair (x=0.0 and 0.6, overlap 0.4): `compute_overlaps`=0.400, resolves to
    centre distance 1.000 (touching). **Works.**
  - BOUNDARY pair (x=2.7 and −2.7, min-image gap 0.6, SAME overlap 0.4):
    `compute_overlaps`=**0.000**, and after 300 steps the pair has **not moved**
    (distance still 0.600). **Broken.**
  So contacts whose closest image crosses a periodic face are invisible to both the
  overlap measure and the position solve. `set_global_scale(2.0)` (which forces the
  ghost band `skin = 1.0*globalScale` to cover these particles) does not help — so it
  is **not** the ghost-emission band width; `step()`→`demStep()`→`generateGhostsKokkos()`
  runs, but the ghost *contacts* are never applied to the real owners. The defect is in
  the ghost-contact narrowphase/position-solve mapping, not ghost emission.
- **Expected:** g(r)=0 for r<d, first peak exactly at contact r=d; boundary contacts
  resolved identically to interior ones; `max_overlap`→0 meaning *actually* no overlap.
- **Workaround (validated):** pack in a **non-periodic, walled** box instead (6
  `add_plane(px,py,pz, nx,ny,nz)` walls, `enable_periodicity(False,…)`). That path gives
  a CLEAN packing (min gap 0.000, dem max_overlap 0.000). Downside: wall-ordering near
  the boundaries and the packing is no longer periodic (so the periodic body-force CFD
  needs rethinking — extract an interior sub-cube, or solve the walled column).
- **Impact on the gallery:** the shipped `random-packed-bed` example's packing is
  therefore invalid (overlapping; φ≈0.66 and Z≈5.1 are inflated). It needs the dem fix
  (proper) or a rework onto the walled path (interim). Flagged for correction.
- **Note:** the distributed `step_mpi` path supplies periodicity via the cross-rank halo
  (different code) and is separately validated, so this is specific to the single-GPU
  periodic self-ghost path.

## Inflow/outflow (profile inlet / BFS) diverges to NaN — advection-driven marginal mode
- **Status:** INVESTIGATING (NOT fixed) — partially improved; deeper open issue. See "Findings".
- **Package / area:** flow — inflow/outflow domain BC + advection (was mis-attributed to the pressure MG)
- **Found in:** scratch run while prototyping `poiseuille-ibm` (the developing
  inflow→outflow channel variant; we shipped the periodic body-force case instead)
- **Observed:** `U_mean=nan`, `max_open_divergence=-inf` after 3000 steps.
- **Expected:** a developed parabola, `u_max/U_mean → 1.5`, finite divergence —
  as `scripts/verify_channel_sdflow.py` produces at its defaults.
- **Repro:** `flow.Solver(L=160, H=24, nz=4)`, `set_mu(U*H/Re)` with `U=1, Re=100`,
  `dt=0.5`, inflow BC face 0 (type 2, U), outflow face 1 (type 3), no-slip ±y,
  `set_pressure_multigrid(True, levels=8)`, `set_pressure_solver_params(80)`,
  `set_pressure_geometry(all-fluid)`; OpenMP backend, 4 threads.
- **Findings (root cause NOT the pressure MG; NOT simply explicit advection):**
  - Bisection: the pressure machinery is fine — **Stokes (advection OFF) is stable to
    machine precision** (div ~5e-15) at the same dt; MG depth and pressure-iteration count
    don't change the blow-up. So the mode is **advection-driven**.
  - The implicit upwind + deferred correction was **gated off for `has_bc_`** (`flow_ibm.hpp`
    `step()`: `if (implicitFou_ && advect_ && !hasBc_)`, "IBM path only … separate milestone"),
    so the domain-BC path ran advection **explicitly**. I wired implicit-FOU through the
    domain-BC path (new `bcStencilPath()` → build the FOU stencil + solve with the cut-cell/FOU
    stencil smoother + reflection ghosts). This is a genuine improvement (channel byte-identical
    under explicit, correct under implicit; cylinder unaffected; BFS survives ~2× longer with
    lower divergence).
  - **BUT it does not robustly cure the BFS.** The divergence shows a **transient spike during
    recirculation development** (peaks ~1e-4 around step 800, then decays as it approaches steady
    state) that is **near-neutral and roundoff-sensitive**: run-to-run (OpenMP reduction order)
    it sometimes decays to a valid steady state (x_r/S≈5.2, correct) and sometimes tips over to
    **NaN**. max|u| stays pinned at the inlet peak throughout — the signature of a **boundary
    mode**, most likely **outflow backflow** (the developing recirculation interacting with the
    zero-gradient outflow) — the "convective outflow" follow-up flagged in flow's CLAUDE.md. A
    separate, deeper numerical-BC project; NOT the immersed-solid bug above.
  - **Literature diagnosis (confirmed):** this is the classical **backflow divergence** at open/
    outflow boundaries. The do-nothing / zero-gradient outflow is only *conditionally* energy-stable;
    when flow reverses across the outlet (`u·n<0`, the developing recirculation/shed vortices), the
    convective term advects undefined exterior data in and injects kinetic energy → divergence.
    Literature signature matches exactly: *"on finer meshes the error concentrates and the mesh
    resolves the instability rather than damping it"* → our resolution dependence (S=8 stable, S=16
    marginal). Refs: Bazilevs et al. 2009; Esmaily-Moghadam, Bazilevs, Marsden 2011 (*A comparison of
    outlet boundary treatments for prevention of backflow divergence*); Dong et al. (energy-stable OBC).
- **Fix (implemented — implicit-advection default + backflow stabilization):**
  1. Implicit-FOU advection is now the **default on the domain-BC (inflow/outflow) path** (via
     `implicitAdv()`); channel stays correct (`u_max/U_mean=1.494`).
  2. **Backflow stabilization** (`flow_ibm.hpp` `applyBackflowStab`): the standard dissipative outflow
     term `+β·ρ·|min(u·n,0)|` added to the normal-momentum diagonal where the outlet reverses (β=0.2
     default, `set_backflow_stabilization`). Purely dissipative + implicit, and **inert where the
     outlet is outgoing** → the channel (no reversal) stays byte-identical.

## Kokkos "deallocated after finalize" warning under Jupyter/Quarto
- **Status:** open
- **Package / area:** packaging / Python bindings (Kokkos teardown order)
- **Found in:** rendering `poiseuille-ibm` (and any interactive `peclet` session)
- **Observed:** at kernel/interpreter shutdown on the OpenMP backend:
  `Kokkos allocation "cnt" is being deallocated after Kokkos::finalize was called`
  plus a backtrace. Harmless (outputs are correct) but alarming and noisy.
- **Expected:** clean teardown with no warning.
- **Repro:** `from peclet import flow; s = flow.Solver(...); s.step()` in a Python
  session, then exit.
- **Notes:** Memory of prior work notes an `atexit` `Kokkos::finalize` is required
  on CUDA (to release View registries before the module unloads); the OpenMP path
  emits this order-of-teardown warning instead. Consider registering the
  `atexit` finalize unconditionally in the bindings so notebooks/CI are quiet.

---

## Pore-space Voronoi mesh: cell collapse + first-order curved-wall gradient
- **Status:** diagnosed; both open (method not yet finished)
- **Package / area:** voro (SDF-walled `meshVolumeOptimize`, experimental / not in PyPI)
- **Found in:** examples/pore-mesh-voronoi
- **Observed:** relaxing interstitial Voronoi seeds toward a target volume collapses cells
  in the tight throats between spheres (cell count drops, gaps appear); the free-energy
  objective `−Σ V_ref·log V` (validated to machine-zero on a wall-free box) STALLS with an
  SDF (line search `alpha→0`).
- **Expected:** cells relax toward `V ∝ V_ref` (uniform, or graded `V_ref=φ³` for a wall
  inflation layer) without collapsing.
- **Repro:** `peclet.voro.optimize_pore_mesh(..., free_energy=True)` on an interstitial seeding →
  the relaxed stages (2 & 4) of examples/pore-mesh-voronoi.
- **Notes:** two root causes. (1) Position-only relaxation can't move seeds *between* pores,
  so an unmatched seeding collapses cells instead of redistributing — mitigated by
  density-graded seeding (`∝ 1/V_ref`) + a hard log-barrier from a feasible start. (2) The
  cell-volume gradient's SDF wall term is exact for a flat wall but only first-order for a
  sphere; on the small free-energy gradient this dominates the direction and stalls the step.
  Fix = an exact tessellator-side wall gradient (the tessellator already publishes the wall
  facet area vectors). See suite memory voro-mesh-optimizer-wall-force.

---

## flow: MG-PCG relative stopping test never fires on a near-quiescent field

- **Status:** worked around (cap `max_iter`); open in flow
- **Package / area:** peclet.flow (pressure MG-PCG driver, all-fluid + domain-BC path)
- **Found in:** examples/rayleigh-benard (onset-of-convection study)
- **Observed:** with velocities ~1e-5 (linear-growth regime just above the RB onset),
  `set_pressure_pcg(True, max_iter, rtol)` runs to `max_iter` on every step regardless
  of `rtol` (1e-2 … 1e-8 all identical): the relative criterion vs the tiny RHS never
  triggers, so a 64x64x32 box costs ~800 ms/step at max_iter=100 where ~40 ms is enough.
  The physics is unaffected (fields bit-identical to a tighter solve; div ~1e-12).
- **Expected:** an absolute-floor (or RHS-scaled) exit so a near-zero RHS solve is cheap.
- **Repro:** RB onset config (laterally periodic, rigid z-walls, Boussinesq closure,
  perturbation 1e-4), watch `last_pressure_iterations()`.
- **Workaround:** cap the work explicitly — `set_pressure_pcg(True, 12, 1e-6)` +
  `set_pressure_warmstart(True)` acts as a fixed-work MG solve (divergence ~1e-12 here).

---

## flow: standalone V-cycle driver ~30x slower than capped MG-PCG at small grids

- **Status:** open (not blocking; PCG is the default single-GPU driver anyway)
- **Package / area:** peclet.flow (standalone V-cycle pressure driver)
- **Found in:** examples/rayleigh-benard (onset-of-convection study)
- **Observed:** with neither PCG nor Chebyshev selected, the standalone driver costs
  ~2.9 s/step on a 64x64x32 all-fluid box (GPU), and `set_pressure_solver_params(6)` vs
  `(10)` changes neither the cost nor the result — the V-cycle count appears not to be
  honoured on this path. Capped MG-PCG does the same projection in ~45 ms/step.
- **Expected:** n_pois fixed V-cycles per step, ~6 ms/cycle at this size.
- **Repro:** same RB onset config with `set_pressure_multigrid(True, 5)` +
  `set_pressure_solver_params(6)` and no PCG/Chebyshev call.

## DEM benchmark: warm-started PGS silently disabled Coulomb friction
- **Status:** resolved (dem `b00c518` interim bound; superseded by cone friction in `f6fb7d2`)
- **Package / area:** dem (velocity solve / friction cluster)
- **Found in:** benchmarks/dem-bulk-dosta2024 (Dosta et al. 2024 silo + drum cases)
- **Observed:** silo discharge identical at mu = 0, 0.3, 0.6, 0.9; drum bed does not circulate
  (Zone-2 species count dead-flat vs the reference codes' large oscillation).
- **Expected:** granular discharge and drum circulation depend strongly on friction.
- **Repro:** any warm-started PGS run; sweep set_material_params friction.
- **Notes:** the Coulomb bound accumulates contact *approach velocities* per velocity iteration
  (solver_friction.hpp accumulateNormalImpulseKokkos); the PGS warm start cancels approaches
  before the loop, so the bound collapses to ~0 for persistent contacts (walls included). Fix
  validated: bound each contact by its manifold's converged PGS impulse (lambdaAcc via a
  contact->manifold slot map) — drum circulation returns, shipped silo 18.1 -> 19.4 k/s. The
  legacy bound was also *inflated* (re-counted the same approach every iteration), so post-fix
  friction is honestly Coulomb-limited. Periodic-ghost duplicate manifolds carry lambda 0 —
  handle before enabling on periodic boxes.

## DEM benchmark: grounded one-sided shock branch too strong for ballistic loads
- **Status:** resolved (dem `f6fb7d2` — staged solve: momentum-conserving sweeps + residual-triggered
  stabilization pass; silo 22.9 k/s, 100k plateau -0.084..-0.091 vs refs -0.090. Residual: the 25k
  floor-limited rebound is suppressed unless `set_stabilization(False)`; see the benchmark entry)
- **Package / area:** dem (gravity statics / shock propagation)
- **Found in:** benchmarks/dem-bulk-dosta2024 (impact + silo cases)
- **Observed:** 5 m/s steel ball (2880:1 mass ratio) stops ~2 mm into a 25k bed with zero
  rebound (references: floor contact at displacement -0.14 then rebound); 100k deep bed arrests
  at -0.023 vs references -0.090; silo discharge ~20% slow (19.4 vs 24.2-24.5 k/s local refs).
- **Expected:** one-sided grounding should only carry quasi-static loads, not shock loading.
- **Repro:** benchmarks/dem-bulk-dosta2024/scripts/case3_impact.py --n 25 (default config).
- **Notes:** disabling the branch (symmetric PGS) restores exact shallow-bed impact but
  over-penetrates the deep bed (-0.137) and makes silo discharge head-dependent — the references
  sit between the two configs in every statics-sensitive observable. Needs a ballistic/approach
  gate (design work, coupled to the tangential-stick item below).

## DEM velocity-level friction lacks tangential stick (sequential impulse)
- **Status:** resolved (dem `f6fb7d2` — friction-cone PGS: accumulated tangential impulse, cone
  projection, warm-started; slab stick + 5/7 roll exact; silo head-independent 22.9 k/s; drum
  amplitude matches refs. Residual: drum circulation period ~1.3-1.5x long — tracked below)
- **Package / area:** dem (friction)
- **Found in:** benchmarks/dem-bulk-dosta2024 (drum amplitude, silo arch strength)
- **Observed:** with the corrected Coulomb bound, drum circulation under-drives (weaker Zone-2
  oscillation than MUSEN/LIGGGHTS) and the symmetric-PGS silo discharges head-dependently
  (41 -> 29 k/s as the head drops; Torricelli-like) at +35% mean rate.
- **Expected:** friction-supported orifice arch => head-independent Beverloo rate (23-25 k/s,
  large/small ratio 3.1); reference-amplitude drum oscillation.
- **Repro:** scripts/case1_silo.py with PECLET_DEM_SYMMETRIC_PGS=1; scripts/case2_mixer.py.
- **Notes:** velocity-level friction needs the accumulated per-contact tangential impulse
  clamped against mu*lambda_n (sequential impulse) to hold static shear.


## DEM drum-mixing circulation period ~1.3-1.5x too long (impulse solver)
- **Status:** RESOLVED (dem `eb89790`, 2026-07-23): the position projection was a second
  normal-force channel invisible to the Coulomb bound, so a jostled bed's friction saturated at a
  fraction of mu*N (wall layer slid 99% of the time at 27-66% of wall speed; Hertz reference
  sticks). Fix: carry the position solve's per-contact normal corrections (impulse units, by pair
  key, quasi-static-gated) into the cone bound. Drum period now matches the references; wall
  co-rotation 0.93-0.97 with 2-4% slip; statics improved. Residual (new, minor): drum peak
  amplitude ~25% low with correct period (rigid stick vs Hertz elastic microslip). The 2026-07-22
  interim analysis below is kept as the record:
- **Old analysis:** missing SUSTAINED-CONTACT tangential elasticity in the
  impulse contact model. The interim geometry-fidelity diagnosis (faceted vs smooth wall) was
  FALSIFIED by a controlled experiment: the new soft-sphere Hertz-Mindlin engine (step_hertz, dem
  915839f — the paper's exact contact model) phase-locks with the references on the SAME smooth
  SDF drum at the verbatim mu_wall=0.2 (and GranOO matched the references with primitive geometry
  in the study itself). beta (collisional tangential restitution) and bulk-mu are null levers; the
  earlier wall-mu=0.4 companion was compensation, not diagnosis. Open design question for the
  impulse model: represent Mindlin-like finite tangential compliance of ENDURING contacts (the
  cone gives rigid stick / kinetic slide only). The Hertz engine remains in-suite as the reference
  physics and as a fast benchmark representation (drum 9.4 min vs LIGGGHTS-24 4.4 h).
- **Package / area:** dem (friction / free-surface avalanching)
- **Found in:** benchmarks/dem-bulk-dosta2024 (case 2)
- **Observed:** with the cone-friction solver the Zone-2 oscillation reaches reference amplitude
  (23.1k vs 22.9-23.1k) but the first peak arrives at ~0.9-1.1 s vs the references' ~0.6 s and the
  second cycle is delayed/damped further.
- **Expected:** bed-circulation period ~2 s matching MUSEN/LIGGGHTS at 2 rad/s.
- **Repro:** benchmarks/dem-bulk-dosta2024/scripts/case2_mixer.py
- **Notes:** amplitude is right, so the bulk is carried; the lag points at the avalanching free
  surface (tangential warm-start strength / manifold-level friction arms on the dilated flowing
  layer). Candidate probes: per-contact (not manifold-averaged) tangential arms; tangential
  warm-start decay on separating-reforming contacts.


## `add_scene_shape` never sizes the contact buffers → dropped contacts, then heap corruption
**RESOLVED 2026-08-30 (peclet-dem `5c53d41`).** The diagnosis below was right and slightly
incomplete: the missing `ensureContactCapacity()` in `add_scene_shape` was one half, and the other
was that the sizing tracked the particle capacity only at *registration* time while `demStep` grows
that capacity on every step. The sizing logic moved out of `Simulation` into a free
`growContactBuffers(Particles&)` which is now called right after `P.ensureCapacity()` in **both**
`demStep` and `demStepMpi`, and `add_scene_shape` calls `ensureContactCapacity()` like every sibling
adder. Gated: kernel ctests 8/8, MPI ctests 24/24, `scene_particle_gate` PASS, plus a new
`contact_capacity_gate.py` — six composed-tree particles dropped from a deliberately small
construction capacity (64) onto an `add_plane` floor come to rest with the lowest centre at 0.2984,
exactly the shell's lowest body-frame point, max overlap 0.0000, against falling through before the
fix. The `pall-ring-packing` page's `Simulation(600)` workaround has been removed.

*(original report below)*
- **Status:** open
- **Package / area:** dem (contact-buffer sizing / composed analytic shapes)
- **Found in:** examples/pall-ring-packing (48 composed analytic rings, 1200-probe shells)
- **Observed:** two symptoms of one cause.
  1. **Silent contact drop.** Register a `SHAPE_SCENE` particle with `add_scene_shape`, add a
     boundary with `add_plane`, and the particles fall straight through it: a 6-ring test ended at
     `ymin = -2.29` after 400 steps with only 3 manifolds. Adding *any* analytic wall — even one
     placed 400 units away, purely as a side effect — makes the SAME plane work
     (`ymin = 0.491`, 14 manifolds).
  2. **Heap corruption mid-run.** At 48 rings × 1625 probes the run aborts inside `step()` around
     step 2000–2200 with `corrupted double-linked list` / `free(): invalid next size` /
     `Segmentation fault` (Python `faulthandler` puts the frame squarely in `s.step(DT)`, not at
     teardown). The bed is healthy at that point — `ymin` stable at 0.50, manifolds plateaued at
     ~238, max overlap 0.006 — so it is not a physics blow-up.
- **Expected:** registering a shape sizes the contact buffers for it, as `add_shape`,
  `add_sdf_wall` and `add_analytic_wall` all do (they call `ensureContactCapacity()`).
- **Repro:** `Simulation(N + 8)` → `add_scene_shape(...)` → `add_plane(...)` → `set_positions` →
  step. Contrast with the same script that also registers a far-away `add_analytic_wall`.
- **Notes / cause:** `Simulation::addSceneShape` (dem `src/sim.hpp`) ends at `uploadShapes()` and
  never calls `ensureContactCapacity()`, unlike every other registration path. Worse, the sizing
  it would use is stale by the first step anyway: `demStep` calls
  `P.ensureCapacity(calculateGhostCapacity(...))` **every step**, and that helper returns
  `nReal + estGhosts + 4096`, so `P_.capacity` jumps from ~56 to >4200 on step 1 — growing every
  per-slot array while leaving every `maxContacts`-sized view at the size derived from the OLD
  capacity. `ensureContactCapacity`'s own comment names this exact failure mode ("any view left at
  the old size is an out-of-bounds write once the count grows past it — silent device corruption
  on GPU, heap corruption on host backends").
  Two candidate fixes, both cheap: call `ensureContactCapacity()` at the end of `addSceneShape`,
  and re-run it whenever `ensureCapacity()` actually grows the capacity.
  **Workaround used in the example:** construct the `Simulation` with a capacity far above the
  particle count (`Simulation(600)` for 48 rings) *and* register an analytic wall after the shape,
  so the contact views are over-provisioned before the first step. With that, 3500 steps run clean.

## Point-shell contacts on a thin-walled concave particle: persistent overlap and a jitter floor
- **Status:** open (modelling limitation, not obviously a bug)
- **Package / area:** dem (point-shell narrow phase)
- **Found in:** examples/pall-ring-packing
- **Observed:** a poured bed of 48 Pall rings (wall thickness 0.12 D, probe spacing 0.030 D — i.e.
  the probes resolve the wall by the usual feature/3 rule) never comes to rest under gravity:
  kinetic energy plateaus at ~1 (against a bed gravitational scale of ~315) and the maximum contact
  overlap sits at 0.05–0.10, i.e. 40–80% of the wall thickness, indefinitely. Raising the position
  iterations 6 → 10 did not fix it. An explicit velocity quench (×0.96 per step for 900 steps) does
  bring it down — overlap to 0.030 (25% of the wall) and KE to ~0.2 — but the bed is quasi-static,
  not static.
- **Expected:** a frictional bed of rigid bodies settling to a static pack with overlaps small
  compared with the smallest feature.
- **Repro:** examples/pall-ring-packing, drop the quench phase from the protocol.
- **Notes:** rings interlock — a rim threads a window, a web enters a bore — so contact regions are
  concave-on-concave, where a point shell registers penetration only once a probe is already well
  inside the other body and the recovery direction is a CSG ridge normal. Hypotheses worth
  separating: (a) probe density is adequate for the wall but not for the *ridge* set; (b) the
  manifold reduction averages contact arms across a genuinely multi-region contact; (c) XPBD
  position projection cannot resolve a mutually interlocked pair in the iteration budget. The
  measured consequence is small for a volume claim — the volume covered by two rings at once is
  0.017% of the bed — but it would matter for a force/stress claim.

---

## dem: the default body–body material is frictionless, and a deep bed leaks through an analytic wall
*(found building `examples/stirred-column`, 2026-08-30)*

**Symptom.** A 20 500-grain bed settling in an inverted-cylinder analytic wall pushed grains
straight through the container: after 1200 settle steps the lowest grain centre was at $y = -0.29$
with the floor at $y = 0$ and a grain radius of 0.4 — i.e. 1.7 radii *below* the floor — and the
outermost centre was 0.5 *outside* the side wall. Once the stirrer started turning, peak grain
speeds reached 41–65 against a blade-tip speed of 10, a four-to-six-fold energy injection.

**Cause.** `add_analytic_wall(..., restitution, friction)` sets the *particle–wall* material, which
I had set. What I had not set was the *body–body* material, and `peclet.dem`'s default is
**frictionless with zero restitution**. A frictionless deep bed behaves like a liquid: it transmits
full hydrostatic pressure to the base and walls, and the XPBD position solve cannot hold that with
the default iteration count, so grains squeeze through the boundary.

**Fix.** `sim.set_material_params(0.2, 0.0, 0.5)`. With friction the same bed, same iteration
counts (4, 4) and same time step gives a minimum wall SDF of **+0.38 against a grain radius of
0.40** (grains resting on the wall, not through it), **zero** escapes, and a maximum grain–grain
overlap of 1e-3. Raising the position-solve iterations from (4,4) to (24,12) and halving `dt`
changed the leakage not at all in the frictionless case, which is what identified the material
rather than the solver as the cause.

**Suggested for the suite.** Either default the body–body friction to something non-zero, or make
`add_analytic_wall` / the first `step()` warn when a bed of more than a few layers is simulated with
`friction == 0`. The failure is silent and looks exactly like a solver-convergence bug, which cost
real time to chase.

**Also noted.** `Simulation.step`'s docstring says "dt=0 uses the configured time step", while the
measured behaviour (recorded in the suite's design notes) is that `step()` with no argument advances
nothing. Whichever is intended, the two disagree — the docstring should be corrected.

## flow: a wall face exactly on a lattice plane makes a MOVING wall silently inert
*(found building `examples/jeffery-orbit`, 2026-08-31)*

**Symptom.** Two plate instances (box leaves, half-thickness 8.0, centred at y = 8 and N−8) driven
with opposite `lin_vel` produced **exactly zero** flow: `max|u| = 0.0` after hundreds of steps,
no error, no warning.

**Cause.** The plate faces sat at y = 16.0 and y = N−16.0 — exactly on lattice planes. A perfectly
grid-aligned face produces **no cut cells**: every cell is fully fluid or fully solid, all
apertures are 0 or 1. The moving-wall no-slip datum enters the momentum operator only through the
cut-cell modification (`ibmModifyStencil` folding `uBc_`), so with no cut rows the wall behaves as
a *stationary* no-slip (the masked-zero coupling) and its velocity goes nowhere. Verified: moving
the half-thickness from 8.0 to 8.3 — faces off the lattice planes — gives the correct Couette
profile with the measured shear equal to nominal to 5e-6 relative.

**Workaround.** Keep analytic-wall faces off lattice planes (any fractional offset works).

**Suggested for the suite.** Either extend the wall-velocity fold to the aligned-face
configuration (the staggered u-point half a cell inside the solid could carry the wall velocity as
its masked value), or detect the case in `set_solid_from_scene` — a moving instance whose surface
produces zero cut cells on some axis — and warn loudly. The failure is completely silent and looks
like "the solver ignores set_instance_motion".

## flow: per-body reaction attribution carried the owner-boundary pressure flux → RESOLVED (flow `1d95260`)
*(found building `examples/ten-cate-sphere`, 2026-08-31)*

A sphere prescribed to translate through the closed ten-Cate tank read **half** its physical drag
(λ = 0.62 against a hard floor of 1.36), while the identical sphere in a single-instance periodic
box read a healthy 1.42. Cause: per-body attribution sums the reaction over the owner partition,
and the pressure flux through the partition's mid-surfaces transfers force between bodies — zero
in the total (pairwise), zero for one instance, cancelling for symmetric arrays, and **worth a
factor 2.2 for a sphere inside a tank**. The same defect gave the Jeffery orbit a −44% period
(spheroid between two plates). Fixed in flow `1d95260` by removing the shared-cell π from both
sides of every cross-owner fluid–fluid face; the 4-sphere gate's per-sphere spread dropped
4.9e-03 → 5.7e-09 (that spread *was* this flux). Anyone comparing per-body forces from a
multi-instance resolved run made before this fix should re-run.

## flow: confined finite-Re moving-body drag is creeping-valued; high-Re coupled fall unphysical → OPEN (suite §7 item 8)
*(found building `examples/ten-cate-sphere`, 2026-08-31 — the page ships as a diagnosed negative result)*

**Symptom.** The ten Cate (2002) settling benchmark fails quantitatively at every Re while every
internal-consistency control passes. E1 (Re 1.5): peak u/u∞ converges resolution-flat
(d/h = 8/12/16) onto ≈0.78 vs measured 0.947 — exactly the *creeping* confined value
(effective K ≈ 1.67 vs the experiment's 1.38). E3/E4 (Re 11.6/31.9): the coupled sphere
accelerates **past u∞** (peaks ≈2.2/1.9 u∞), which no drag law permits.

**Probe ladder** (all at d/h = 8 unless noted; scripts tc_probe*.py, session scratchpad):
- dt ×½, velocity sweeps 60→200, SOU→Koren TVD: E1 plateau unchanged (0.781/0.779/0.781/0.785).
- Advection OFF: 0.794 — advection contributes ≈nothing at Re 1.5 where the experiment needs +19%.
- **Tow probe** (prescribed U = 0.947 u*, no dem): F/W = 1.244 — consistent with the free fall
  (1.244·0.777/0.947 = 1.02) and ≈ the creeping confinement correction 1/0.76.
- **Periodic control** (no tank, back-pressure body force): settles at 1.032 of the screened
  expectation — the solver is healthy unconfined; the defect needs the tank.
- **Newton audit** (towed E4): F_sphere + F_tank = **+0.32 W** with advection on (−0.001 W at E1
  with advection off) — the advective momentum budget leaks at the moving cut wall.

**Diagnosis (2026-08-31, superseded in part — see the update below).** All one suspect: the
advective momentum flux through the moving cut wall — the O(h) wall term §7 item 8 of
suite/docs/ANALYTIC_SDF_GEOMETRY.md measured at −0.4…−1% on a STATIC bed and deliberately
reported-not-fixed. For a moving body it is two orders larger and kills both the inertial
screening of the wall correction (E1/E2) and outright momentum conservation (E3/E4).
Fix = momentum-operator work in flow (conservative cut-wall advective flux with wall velocity),
not example work. The page is the regression test waiting for it.

**UPDATE 2026-08-31 — the fix landed and this page did NOT recover.** `peclet-flow fb1a1a7`
(rung A0 of `flow/doc/advective_cutwall_flux_plan.md`) feeds the local rigid-body wall velocity
into the momentum advection's inputs, on both the explicit and the implicit-FOU paths. Static
scenes are byte-identical (60/60 MPI ctests, regression +0.00%); `PECLET_FLOW_ADV_WALLVEL=0` is
the ablation. What it fixed, and what it did not:

- **Fixed — the momentum leak.** Newton audit, towed E4: `F_sphere + F_tank` **+0.32 W → −0.033 W**,
  now smaller than the same probe's advection-OFF residual (−0.070 W). Towed E4 drag
  **1.544 → 1.087 W**.
- **Fixed — finite-Re moving-body drag against an external reference.** The `moving-sphere-drag`
  page's Blackburn (2002) peak `Cd` ladder: **+10.16 / +10.27 / +2.10 / −0.42 / +6.71 % →
  −0.76 / −0.66 / −2.13 / −2.17 / −0.54 %**. Worst case 10.3 % → 2.2 %.
- **NOT fixed — this benchmark.** E1 peaks (d/h = 8/12/16) **0.781 / 0.777 / 0.749 →
  0.803 / 0.797 / 0.766** against the measured 0.947, still resolution-flat; E3 / E4 peaks
  **2.16 / 1.87 → 2.03 / 1.77 × u∞**, still above u∞. Re-rendered with zero page edits.

So the confined finite-Re drag deficit is **not** the advective cut-wall flux. Three new leads
replace the old diagnosis: (1) towed and free-falling now DISAGREE at E4 — the towed sphere's
drag exceeds its weight at 0.955 u*, which predicts a terminal velocity below u∞, while the
coupled fall peaks at 1.77 u∞ (at E1 the two agree to 2 %), so the coupled loop or the transient
is the suspect at high Re; (2) the unconfined periodic control moved **1.032 → 1.084**, i.e. the
wall-velocity extension changes the drag ~5 % on a body nowhere near a confining wall; (3) the
Blackburn ladder is now flat at −0.7…−2.2 % where it used to converge — a small
resolution-independent deficit replaced a large resolution-dependent excess. **The page's closing
prediction ("E1's ladder should climb from 0.78 toward 0.947 and E3/E4's peaks drop below u∞")
is now measured false and needs rewriting before the new numbers are published.**

**Two traps fixed en route, kept for reuse:**
- Grid sizes must feed the 4-level MG factors of two: the original NX=62 tank (one factor of 2)
  ran 10× slower per step than NX=64 (549 s vs 56 s per E1-d/h=8 fall).
- Explicit resolved coupling at ρp/ρf = 1.15 rings and near-floor diverges: the standard
  virtual-mass stabilizer (integrate with m + ma, add the lagged ma·a back, ma = 2ρfVp) removes
  it without touching converged dynamics; the post-peak stop must arm only past 0.6 u* or the
  start-up transient's dip triggers it (bit the d/h=16 rung: 160-step run, peak 0.41).
