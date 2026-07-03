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
