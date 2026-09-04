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

## `max_open_divergence()` returns exactly 0 without geometry — so `advect_vof`'s divergence guard is silently inert on a bare box
- **Status:** RESOLVED (flow WO-R2, `advect_vof` now throws without a cut-cell pressure operator and uses `max_open_divergence_projected()`; 2026-09-03)
- **Package / area:** flow (VoF transport / cut-cell diagnostics)
- **Found in:** examples/vof-advection-benchmarks
- **Observed:** `advect_vof(dt)` documents that it "THROWS if the current velocity is not
  discretely divergence-free to 1e-10 (`max_open_divergence()`)". `maxOpenDivergence()` early-outs
  with `return 0.0` when `cutcellPressure_` is false (`flow_ibm.hpp:1912`), which is the state of
  any solver that has not been given a `set_solid` / `set_pressure_geometry`. On such a solver a
  deliberately non-solenoidal field (the LeVeque field sampled at CELL CENTRES,
  `max|div| = 0.612` measured in NumPy) is accepted without complaint: 50 kinematic steps then
  lose **4.93 % of the liquid volume**, quietly, with the interface still looking plausible.
- **Expected:** the guard fires whenever the field is not divergence-free, geometry or no geometry
  — or, failing that, `advect_vof` refuses to run at all without a pressure geometry, so the
  contract in the docstring is never silently void.
- **Repro:** `s = flow.Solver(32,32,32); s.enable_vof(); s.set_vof(C0); s.set_state(uc,vc,wc)`
  with a cell-centre-sampled field, then `s.advect_vof(dt)` — no throw. Add
  `s.set_pressure_geometry(np.full((32,32,32), 10.0, order="F"))` before `enable_vof` and the same
  call raises with `max|div(open*u)| = 0.61191 > 1e-10`.
- **Notes:** same root cause as the bidisperse-bed entry below (a bare box has no cut-cell
  operator, so every openness-weighted diagnostic early-outs). The page works around it by always
  calling `set_pressure_geometry` with an all-positive SDF, which costs nothing and makes the
  diagnostic live; that workaround is written into the page as an explicit instruction.

## The interface-local Courant band has no wisp guard, so a long run's reported CFL creeps to the global maximum
- **Status:** RESOLVED (flow WO-R2 item 4b: the band predicate uses `wispEps`, set to 1e-8 by `enable_vof`; Zalesak's reported CFL now tracks the a-priori bound; 2026-09-03)
- **Package / area:** flow (`vof/advect_wy.hpp`, `maxCourantInterface`)
- **Found in:** examples/vof-advection-benchmarks §4 (Zalesak, 1000 steps)
- **Observed:** the Courant band is "mixed cells and their face neighbours", with neighbours
  compared by exact inequality (`c(i-sx) != ci`). Weymouth–Yue leaves round-off colour residue
  behind the interface (min C = −3.8e-17 after 1000 steps), and a cell holding 1e-17 differs from
  a neighbour holding 0, so the band creeps outward along the interface's wake. On the Zalesak
  case `vof_last_courant()` reads **0.2545** after the first step (the true interface value) and
  **0.3110** by the end — the *global* maximum of the field, which is what the interface-local
  measure exists to avoid. The run therefore needs `set_vof_cfl_limit(0.5)` even though the
  interface itself never exceeds 0.255, and the ctest does the same thing for the same reason.
- **Expected:** the band predicate uses a wisp threshold, the way the interfacial predicate
  already does (`set_vof_interface_eps`, default 1e-8, added for the curvature cascade at V3).
- **Repro:** the `zalesak-run` cell of the page; print `s.vof_last_courant()` each step.
- **Notes:** conservative in the safe direction (it over-estimates), so it is a usability defect
  rather than a correctness one — but it silently converts a legitimate benchmark setup into a
  throw, and `vof_max_courant()` (which uses the same predicate on the CURRENT field) will size a
  dt that `advect()` then rejects a few hundred steps later.

## `vof_advect_scenes.hpp::fillRotation` samples v half a cell off the face centre
- **Status:** open (cosmetic — the gate it serves is unaffected)
- **Package / area:** flow (tests/kokkos/vof_advect_scenes.hpp)
- **Found in:** examples/vof-advection-benchmarks §1, while transcribing the scene to NumPy
- **Observed:** the advector's `vf(j)` is the HIGH y-face of cell j and sits at
  `x = (i + 1/2) h`, but `fillRotation` writes `v(i) = omega * ((gx + 1.0) * h - cx)` while the
  companion `u` correctly uses the y cell centre `(gy + 0.5) * h`. The prescribed field is
  therefore a rigid rotation about `(cx - h/2, cy)`, not about `(cx, cy)`.
- **Expected:** `omega * ((gx + 0.5) * h - cx)`.
- **Repro:** read `vofscene::fillRotation`; or run the Zalesak case both ways — the page measures
  L1/V **2.784e-2** with the centred sampling against the ctest's recorded **2.807e-2**.
- **Notes:** harmless for the gate it serves, and provably so: a *full* revolution is the identity
  map about any centre, so the exact solution at the final time is the initial condition either
  way and the two shape errors agree to 1 %. It would matter for a partial revolution, or for any
  test that compares intermediate positions.

## WO-E finding 2 is a recipe, not a theorem: the LeVeque field sampled pointwise ON THE FACES is already discretely solenoidal
- **Status:** open (documentation nuance)
- **Package / area:** flow (VoF, `doc/vof_workorders.md` WO-E finding 2)
- **Found in:** examples/vof-advection-benchmarks §3
- **Observed:** WO-E finding 2 states that pointwise sampling of the LeVeque field "would pin the
  conservation floor at O(h^2)", which is why the test scenes build it as the discrete curl of an
  edge vector potential. Measured: the same field sampled **pointwise at the staggered face
  centres** has `max|div| = 3.20e-14` at 32³, i.e. round-off, not O(h²). It is an exact identity —
  `sin^2(pi x_{i+1}) - sin^2(pi x_i) = sin(2 pi x_{i+1/2}) sin(pi h)` applied to each of the three
  terms makes the divergence cancel as `2 - 1 - 1`. Sampling at CELL CENTRES (the natural reading
  of the paper) does give the O(1) failure the finding describes: `max|div| = 0.612`.
- **Expected:** nothing to change in the code — the vector-potential construction is still the
  right general recipe, and it is what makes the scene builders correct for *any* field. The
  finding's wording overstates the specific claim about this field on this mesh.
- **Repro:** the `divergence-guard` cell of the page.
- **Notes:** recorded so a future reader does not conclude the vector potential is load-bearing
  for the recorded 5.7e-14 drift at 128³. It is not: the drift would be the same with the
  face-pointwise sample. It IS load-bearing as a method.

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
- **Status:** RESOLVED — examples `a27ed09` (2026-07-03, page rewritten pointwise, log-log plot dropped) + flow `6f0a312` (2026-07-03, `verify_poiseuille_sdflow.py` → `verify_poiseuille_flow.py`, pointwise node metric); re-verified 2026-09-04 on OpenMP and CUDA (see the updates at the end of the entry)
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

**Update 2026-09-04 — both fixes confirmed done, entry closed.** (1) examples `a27ed09`
rewrote `examples/poiseuille-ibm` around the pointwise node comparison (staggered and
collocated), replaced the convergence plot by the exact-at-every-resolution table and kept the
`u.max()`-vs-`U_max` trap as a callout. (2) flow `6f0a312` renamed the script to
`scripts/verify_poiseuille_flow.py` and made it assert `max_node |u − u_analytic| < 1e-4` on
both meshes. Re-run today on the flow `rel-issues` branch (OpenMP, 4 threads): node error
**6.49e-8 / 1.10e-6 / 2.47e-5** at N = 16/32/64 (u_max 0.45 / 1.8 / 8.5 — the error scales with
u_max, i.e. it is the cut-cell closure's float floor, ~2.5e-6 relative, not discretization
error), identical on the staggered and collocated meshes, PASS. The same exactness fact is
now also the reference of the new free-slip gate (`tests/kokkos/test_freeslip.cpp`, entry
"flow: no free-slip domain BC" below): a half channel closed by a symmetry plane reproduces the
full channel node for node to 3e-13.

**Verification 2026-09-04 (landing session, flow main `b7669d3`).** `scripts/verify_poiseuille_flow.py`
re-run on CUDA against the merged tree: node error 6.491e-8 / 1.100e-6 / 2.468e-5 at N = 16/32/64,
staggered and collocated identical, PASS — the same digits as the OpenMP run above, so the metric is
the pointwise one on both backends and the entry stays closed.

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
- **Status:** RESOLVED as a blow-up (not reproducible on flow main, 2026-09-04 sweep on OpenMP + CUDA); the conditionally-stable outlet-reversal regime is now instrumented (flow `eda0029`: `outflow_backflow()` census + a one-time warning + `tests/kokkos/test_outflow_backflow.cpp`; merged to main 2026-09-04, verified — see the last update). See the update at the end of the entry.
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

**Update 2026-09-04 — re-measured on today's main; no divergence anywhere; mechanism
instrumented.** Runs on the flow `rel-issues` branch, shipped as `eda0029` (OpenMP 4 threads; dt = 0.4 also on CUDA):

| configuration | steps | result |
|---|---|---|
| the entry's repro: uniform-inlet channel L=160 H=24 Re=100 dt=0.5, MG 8 lv, 80 p-iters | 3000 | steady, `u_max/U_mean` 1.491, KE 8.936e3 flat, div 1e-8 |
| BFS S=16 (`verify_bfs_sdflow.py` scene) Re_S=100, dt 0.4 / 0.8 / 1.6 | 6000 / 6000 / 1500 | steady, x_r/S 5.31 all three, div 2e-16 |
| BFS Re_S=200, dt 0.4, with / without backflow stabilization | 6000 | **bit-identical** (KE 5.8667798e3 both, x_r/S 8.12): no outlet reversal, so the term is inert |
| BFS Re_S=800, dt 0.4 and 0.8 (β = 0.2) | 6000 | finite; the bubble reaches the outlet (x_r/S = 12 = L/S), outlet reversed over part of its height, KE bounded |
| BFS Re_S=800, dt 0.4, **β = 0** | 6000 | finite; same picture |

So (i) the original NaN was the explicit advection the domain-BC path ran before flow
`4e53522` wired implicit FOU + deferred correction + backflow stabilization through it — the
entry's own bisection (Stokes stable, advection-driven) already said so; (ii) the "marginal,
roundoff-sensitive" mode the entry left open, and the `dt=0.4` warning in the BFS script,
are not reproducible on main (dt 0.4 → 1.6 all steady); (iii) the one genuinely
energy-injecting configuration is a **reversed outlet** — the literature's conditionally-stable
do-nothing regime (Esmaily-Moghadam, Bazilevs & Marsden 2011): the zero-gradient ghost
re-enters the boundary cell's own velocity, an advective source with no sink, energy
production Σ ρ (u·n)₋ |u|²/2. Measured at Re_S = 800 when the recirculation tail crosses the
outlet: a bounded transient excursion of max|u| to **1.28× the inlet peak on the outlet column
(x = L−1)**, with β = 0 (1.909) and the default β = 0.2 (1.897) alike — at this Re the
stabilization (β ρ |u·n| on the diagonal, ≈ 5 % of ρ/Δt) does not decide boundedness, and the
run stays finite either way. Not found: any divergence. (S = 32 at Re_S = 200 was started and
abandoned at 300 steps — too slow on the loaded host — so the entry's "finer meshes are worse"
claim is untested today.)

What ships instead of a fix (there is nothing to fix on the measured cases): flow
`outflow_backflow()` returns the census over the outflow faces (max reversed normal velocity,
reversed area fraction, energy influx; collective under MPI), `step()` warns **once** on stderr
when reversal appears with the stabilization switched off (`set_backflow_stabilization(0)`),
naming the mechanism and the β ≥ ½ bound, and `tests/kokkos/test_outflow_backflow.cpp` gates the
plumbing (a half-reversed outlet reports fraction 0.5 and max_reverse ≈ U; a developing
channel and a periodic box report zeros). The BFS script keeps dt = 0.2 for its recorded
numbers, with its comment corrected to today's measurements.

**Update 2026-09-04 (landing session) — census merged to flow main (`eda0029`), re-measured
independently; it is a detector, not a fix.** The entry's own repro (`Solver(160,24,4)`, U = 1,
Re = 100, dt = 0.5, uniform inlet / outflow / no-slip ±y, MG 8 levels, 80 pressure iterations,
all-fluid geometry, OpenMP 4 threads, 3000 steps) is steady with the default β = 0.2 **and** with
β = 0, bit-identical to each other (KE 8.936169e3, outlet `u_max/U_mean` 1.4910, div 3e-8): the
outlet never reverses, the census stays 0/96, the warning never fires, and there is no blow-up to
precede — the NaN belongs to the pre-`4e53522` explicit advection and is not reproducible.
Where the outlet *does* reverse (BFS S = 16, L = 12 S, Re_S = 800, dt = 0.4, β = 0) the warning
fires at **step 693**, at the first reversed face (max u·n = −9.9e-4, 3.1 % of the outlet
area, energy influx 2.4e-9), long before anything grows; the run then stays finite over 6000
steps but is **not steady**: reversal comes and goes in episodes (reversed fraction up to 0.34,
`u_out,min` down to −0.77, energy influx up to 2.9 at step 2000), during which
`max_open_divergence` rises from 1e-6 to 1e-2 (the 80-iteration pressure cap is hit) and KE
drifts between 6.9e3 and 7.6e3; β = 0.2 gives the same picture (`u_out,min` −0.43 vs −0.61 at
step 6000, KE 7.38e3 vs 7.40e3). So the stabilization does not decide boundedness here
either, and the conditionally-stable regime is *reported*, not removed — a convective (or
energy-stable, Dong-type) outflow remains the fix if a case ever needs one. Byte-identity where
the census does not trigger: `verify_channel_sdflow.py`'s configuration and the
`cylinder-vortex-street` page's (β = 0.5) run 300 steps bit-identical to flow main before the
merge (u, v, p on OpenMP 4 threads; a same-build control also identical) — the census only runs
inside `step()` when β ≤ 0. Full matrix on the merged tree: `tests/kokkos` 36/36 CUDA /
36/36 OpenMP, `tests/kokkos_mpi` 103/103 at np = 1,2,4, regression suite within baseline
(0.00 % on every metric), the five verify scripts PASS (`verify_bfs_sdflow.py` included).

## Kokkos "deallocated after finalize" warning under Jupyter/Quarto
- **Status:** RESOLVED 2026-09-04 — core `c1df85a` (new `peclet/core/python/kokkos_teardown.hpp`,
  Releasable zero-copy capsules in `ndarray_interop.hpp`), flow `3035320`, dem `90366c0`,
  voro `2c2e819`, pnm `af0c692`, coupling `684513e`. **Root cause:** it was never a harmless
  warning — `Kokkos::Impl::SharedAllocationRecord::decrement` calls `Kokkos::abort` (SIGABRT,
  exit 134) on OpenMP exactly as on CUDA; the Jupyter kernel's fd capture swallows the message,
  so only the text was seen. Python runs `atexit` hooks (where `Kokkos::finalize` must live, for
  CUDA) BEFORE it tears down module globals, so a `Solver`/`Simulation` or a zero-copy
  `*_view` array still referenced at exit — a script global, `python -c`, every notebook — freed
  its Views after finalize. flow had no live registry at all; no module released the
  `view_to_ndarray` capsules; coupling never finalized its Kokkos. **Fix (one pattern for all
  six modules):** every bound View owner is a `Releasable` (registered on construction), every
  zero-copy capsule is one too, and each module's single atexit hook (also `<module>.finalize()`)
  releases them all and THEN finalizes. Measured with a teardown harness — 6 modules x {script,
  `python -c`, `del`, `sys.exit()`, ipykernel} x {OpenMP, CUDA}: before, flow/dem/coupling
  rc = -6 in every mode except explicit `del`; after, all 60 cells silent, exit 0. Nothing needs
  `del` before exit; after an explicit `finalize()` a solver call raises `TypeError` and the
  `*_view` arrays must not be read. Two pre-existing sharp edges seen on the way, NOT fixed here:
  `peclet.core.amr.Flow.step()` without any `set_solid` segfaults, and a Python-callable
  `set_solid` deadlocks under the OpenMP host backend (Kokkos worker threads call back into
  Python without the GIL) — use `set_solid_spheres`.
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
- **Status:** cause (1) ADDRESSED 2026-09-04 by `peclet.voro.redistribute_pore_mesh` — the
  topological loop (split / merge / relax / wall re-seed) reaches a uniform target within ~10 %
  per cell (rms 0.04) from a 2x mismatched start with zero dead cells, and rms 0.08 for a
  wall-graded target of slope 0.3 (the first wall shell stays ~1.5x above target; the original
  `clip(φ)` target is unresolvable — neighbouring targets 8x apart). See
  examples/pore-mesh-redistribution. `optimize_pore_mesh` still cannot polish from there
  (collapses cells); its `sw=6` on a few hundred seeds segfaulted (fixed: the search window is
  clamped to the grid). Cause (2) open for the optimiser; the FLOW solver on the same meshes
  uses a wall-anchored quadratic wall gradient (examples/voronoi-sphere-drag).
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

**Update 2026-09-02 — root-caused and detected (suite §7 item 12).** A staggered point with sdf
exactly zero is fluid to the mask (strict < 0) and not a ghost to the cut-cell fold (strict < 0):
the wall has no row. `set_solid_from_scene` now warns and `moving_instance_degenerate_points()`
counts them; gate `lattice_plane_gate.py`.

**Suggested for the suite (original).** Either extend the wall-velocity fold to the aligned-face
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

## flow: no free-slip domain BC, so the Hysing benchmark's lateral condition can only be approximated
- **Status:** RESOLVED — flow `e6c2c4e` (2026-09-04, merged to main the same day, verified — see the last update): `set_domain_bc(face, 4)` = free-slip / symmetry plane, both grids, MPI; gates in `tests/kokkos/test_freeslip.cpp` + `test_velocitymg_bc_mpi`. The pages still run with periodic sides (see the update at the end of the entry)
- **Package / area:** flow (domain boundary conditions, `set_domain_bc`)
- **Found in:** examples/rising-bubble
- **Observed:** the Hysing et al. (IJNMF 60:1259, 2009) rising-bubble benchmark prescribes
  **free-slip** side walls (and no-slip top/bottom). `flow`'s `set_domain_bc` offers
  0 periodic / 1 wall (no-slip) / 2 inflow / 3 outflow — there is no free-slip (symmetry)
  type, so the prescribed lateral condition cannot be imposed.
- **Expected:** a symmetry/free-slip domain BC (zero normal velocity, zero normal gradient of
  the tangential components), which is the standard companion of no-slip in any benchmark suite.
- **Workaround used (and why it is exact for case 1):** the page runs with **periodic** sides.
  Mirroring a laterally symmetric bubble about x = 0 and x = 1 places its images at spacing 1,
  and the mirror of a symmetric bubble is its translate — so while the lateral symmetry holds,
  periodic and free-slip are the same problem. Case 1 stays symmetric for the whole 3 s and the
  measured centroid lands within 0.02 % of the reference. Case 2 grows skirts and filaments that
  break the symmetry, so there the substitution *is* an approximation and part of that case's
  ~2.6 % centroid deviation belongs to it.
- **Notes:** a free-slip type would also remove the same substitution from the capillary-wave and
  droplet-oscillation cases in `flow/tests/study/vof_surface_tension.py`. Low risk: it is a
  boundary stencil, not a solver change.
  **Also hit by examples/capillary-oscillations (2026-09-02):** the standing capillary wave's
  $\pm z$ boundaries are no-slip walls where the exact dispersion relation assumes only
  impermeability (the walls enter it as the added-mass factor $\tanh kH$ alone). Here it is
  quantitatively harmless — the wall Stokes layer is $\sqrt{\nu/\omega_0} \approx 0.3$ cells
  against a wall $H = 16$ cells from the interface, and the measured frequencies land within
  0.54 % of the exact root — but it is the same missing boundary type, and the drop case avoids
  it only by being fully periodic.

**Update 2026-09-04 — implemented (flow `e6c2c4e`).** `set_domain_bc(face, 4)` is a free-slip /
symmetry plane: zero normal velocity, zero normal derivative of the tangential components,
pressure Neumann like a wall (`vx/vy/vz` ignored). Staggered: the normal component is the
no-slip treatment with wall velocity 0, the tangential ghost the *even* reflection (or a
dropped face with −β on the diagonal on the implicit fold path); collocated: odd reflection of
the normal component, mirror of the tangential ones. It runs through every momentum path
(const-coefficient fold, cut-cell/FOU stencil, mixed velocity MG) and is rank-owned under MPI.
Measured gates: a half Poiseuille channel (cut-cell SDF wall + type-4 face) equals the full
channel **pointwise to 3e-13 (staggered) / 7e-13 (collocated)** on either side of the axis;
a body-force-driven flow along four slip faces stays uniform with v = w = 0; a Stokes sphere in
a ±y slip box equals its mirror-periodic twin (sphere + image, twice the height) to 6.1e-13
through the pressure solve; `test_velocitymg_bc_mpi` gains a ±z free-slip pass, np=1 bit-exact,
np=2/4 at 1.6e-14. Two solver facts the implementation exposed and fixed: the SDF ghost band
beyond a non-periodic face is the periodic wrap of the *opposite* side (a phantom solid on a
symmetry plane; now mirrored for type 4, other types unchanged), and the velocity multigrid's
coarse levels must not carry the exact Neumann fold at small ρ/Δt (nearly singular coarse
operators; measured 1.2e-3 → 2.5e-7 residual after 32 V-cycles). **Not done here:** switching
`examples/rising-bubble` (Hysing case 2), `examples/capillary-oscillations` and
`flow/tests/study/vof_surface_tension.py` from periodic to type-4 sides — that is a re-render of
the pages with a two-phase (VoF) solver, which the VoF session owns; the pages keep the periodic
substitution and its stated caveat until then.

**Verification 2026-09-04 (landing session) — merged to flow main as `e6c2c4e` (+ `eda0029` census,
`e5e1bbf`/`b7669d3` notes).** The branch was re-verified from scratch before the merge, on fresh
build trees. Physical gate (Python, `flow.Solver` and `SolverColocated`, the
`verify_poiseuille_flow.py` geometry — cut-cell walls at half-integers, N = 16/32/64): the half
channel closed by a type-4 face on the +y side and, separately, on the −y side equals the full
channel **node for node to 2.5e-13 / 3.4e-12 / 2.6e-11** (u_max 0.44 / 1.79 / 8.44), with the
same parabola node error as the full channel (6.49e-8 / 1.10e-6 / 2.47e-5, the float-closure
floor) and v = w = 0 exactly; identical digits on both grids and on OpenMP and CUDA. A uniform
tangential flow along four free-slip faces (periodic x, advection on, 50 steps) stays uniform to a
**spread of 7e-12** (body-force-driven u = F t/ρ and a uniform initial u alike) with |v|, |w| ≤
2e-13; the residual drift from the exact value (1.3e-6 relative, forced; 1.1e-6, uniform IC) is
the momentum operator's float-storage floor — a fully periodic control box with no BC at all
drifts by the same 3.3e-7 / 2.6e-6. `vof_issues_sweep.py freeslip` passes unchanged (discrete
parabola 1.2e-10, symmetry-plane equality 9.7e-13). Matrix: `tests/kokkos` 36/36 CUDA /
36/36 OpenMP (`freeslip`, `outflow_backflow` included), `tests/kokkos_mpi` 103/103 at
np = 1,2,4 with the free-slip pass of `test_velocitymg_bc_mpi` bit-exact at np = 1 (0.0) and
1.6e-14 / 1.4e-14 at np = 2 / 4, slip plane exactly impermeable; regression suite 0.00 % on
every metric; the five verify scripts PASS.

## flow: the VoF interface length/area is not exposed, so benchmark "circularity" cannot be reported
- **Status:** RESOLVED (flow WO-P3c/P3d: `vof_interface_area()`, joined marching-tetrahedra sheet on the PLIC level set, exact to 1e-4 on spheres; the rising-bubble page can now report circularity — not yet done on the page)
- **Package / area:** flow (VoF / PLIC reconstruction bindings)
- **Found in:** examples/rising-bubble
- **Observed:** the Hysing benchmark tabulates three quantities — centroid, rise velocity and
  **circularity** (the perimeter of an area-equivalent circle over the actual perimeter). The
  first two follow from `get_vof()` and `get_w()`; the third needs the length/area of the
  reconstructed PLIC interface, which the solver computes internally (the reconstruction is what
  the geometric fluxes and the curvature cascade are built on) but does not expose to Python.
- **Expected:** something like `vof_interface_area()` (a per-cell field, or the global sum) so a
  page can report circularity/sphericity and, more generally, wetted or interfacial area — which
  is also the quantity a trickle-flow or wetting example will want.
- **Workaround used:** the page reports the two computable quantities and states plainly that
  circularity is omitted and why.
- **Notes:** the per-cell PLIC polygon area is already formed inside `plic.hpp`; the missing piece
  is a reduction plus a binding.

## flow: on the collocated grid `set_state` + `advect_vof` silently advects with a ZERO face field
- **Status:** **RESOLVED** (flow `ec18744`) — `set_state`/`set_velocity` now seed the MAC face
  field through the same `centerToFace` map `project()` uses, so the kinematic entry point
  means the same thing on both grids AND the divergence guard finally measures something
  (the LeVeque field seeded that way reads max|div(open uf)| = 2.5e-14, and 10 kinematic steps
  give a colour BITWISE equal to a staggered `Solver` handed the same face field). A face field
  that was never built at all is refused with a message naming the fix.
- **Package / area:** flow (VoF transport on `SolverColocated`, rung V8)
- **Found in:** examples/vof-advection-benchmarks (the collocated cross-check)
- **Observed:** on `SolverColocated` the colour is advected by the projected MAC face field
  `uf_/vf_/wf_`, which only exists after a projection. `set_state` writes the **cell** velocity and
  leaves that face field untouched, so on a fresh solver it is all zeros. `advect_vof(dt)` then
  runs happily: its guard tests `max_open_divergence()`, which reports the *face* field's residual,
  and a zero field is perfectly divergence-free. Measured on the LeVeque case at $32^3$:
  `set_state(u,v,w)` with `max|u| = 63.3`, then `max_open_divergence() = 0.0`, `max|uf| = 0.0`, and
  after `advect_vof(0.01)` the colour is unchanged to the last bit (`max|C - C0| = 0.0`). No throw,
  no warning, and a benchmark loop written the staggered way produces a perfectly "conservative"
  run in which nothing ever moves.
- **Expected:** either `advect_vof` refuses to run on a collocated solver whose face field has
  never been built (a "call step()/project() first" throw, the way it already throws on a
  non-solenoidal field), or `set_state` seeds the face field via `centerToFace` so the kinematic
  entry point means the same thing on both grids.
- **Repro:**
  `s = flow.SolverColocated(32,32,32); s.set_pressure_geometry(np.full((32,)*3, 10.0, order="F"));
  s.enable_vof(); s.set_vof(C0); s.set_state(u,v,w); print(s.max_open_divergence(),
  np.abs(s.get_uf()).max()); s.advect_vof(0.01)`.
- **Notes:** the page works around it by driving the collocated run through `step()` (which
  projects, and therefore builds the face field, before advecting) and mirroring `get_uf/vf/wf`
  into a staggered `Solver` for the bitwise comparison. There is no exposed `project()` binding, so
  `step()` is the only way to seed the face field from Python today — worth exposing one.

## flow: the mode-2 drop oscillation frequency is ~4 % low — inviscid, resolution-independent, unattributed
- **Status:** open (published on the page as a measured deviation, not tuned away)
- **Package / area:** flow (geometric VoF — curvature cascade and/or Weymouth–Yue transport of a
  *curved* interface; the balanced-force CSF itself is exonerated)
- **Found in:** examples/capillary-oscillations, part B
- **Observed:** a prolate-perturbed drop ($R = 8$ cells, $48^3$ periodic box, drop/box volume
  ratio 1.9 %, $\varepsilon = 0.05$, matched fluids, $\sigma = \rho = 1$) rings in mode 2 at
  $\omega = 0.09142$ ($\mu = 0.0025$) and $0.09072$ ($\mu = 0.02$) against Lamb's inviscid
  $\omega_0 = 0.09682$ — **−5.58 % / −6.30 %**. The *exact* viscous mode (Miller & Scriven 1968,
  computed on the page) accounts for only −1.78 % / −5.03 %, leaving **−3.87 % / −1.34 %**. The
  low-viscosity rung is the meaningful one: at $\mu = 0.02$ the run does not contain the whole
  viscous shift being subtracted from it (its fitted damping is 17 % below the exact rate, because
  the interfacial boundary layer $\sqrt{\nu/\omega_0}$ is 0.45 cells — 0.16 cells at
  $\mu = 0.0025$). So **≈ 4 % of inviscid frequency deficit is unexplained**.
- **Expected:** the same benchmark's planar sibling on the same machinery closes cleanly — the
  standing capillary wave matches the exact viscous two-fluid root to −0.02 / −0.19 / +0.54 % at
  32/64/32 cells per wavelength (page part A). A curved interface should not be 4 % off when a
  flat one is 0.2 % off.
- **Repro:** `oscillating_drop(48, 8.0, 0.0025)` on the page, or
  `PYTHONPATH=<build> python tests/study/vof_surface_tension.py lamb` in the solver repo; the
  exact references are `tests/study/vof_capillary_references.py`.
- **Notes — what it is NOT** (each ruled out by measurement, VoF campaign 2026-09-02):
  the reference (the exact viscous root is subtracted above); the measurement (the
  damped-sinusoid fit and the zero-crossing estimator agree to 0.01 %, and the polar half-height
  and equatorial half-width give −5.7 / −5.0 % against the moment's −5.6 %); confinement (an
  eightfold reduction of the drop/box ratio moves it 0.6 %); resolution (the residual is
  −3.9 / −3.4 / −3.9 % at $R = 8/12/16$ in $48^3/72^3/96^3$ — it does not converge away);
  the amplitude ($\varepsilon = 0.10 \to 0.01$ extrapolates to ≈ −6.1 % at $\varepsilon = 0$);
  the time step (a fourfold reduction moves it 0.03 %); and — the surprise — the curvature
  estimator, since freezing $\kappa$ to the exact curvature of the moment-fitted spheroid makes
  the deficit **larger** (−9.0 %), the height-function cascade's +3 % $P_2$ over-estimate having
  been partly compensating. The untested link is the **transport**: whether WY advection of a
  curved interface by the mode's own velocity field moves the $P_2$ moment at the exact rate — a
  kinematic test with a prescribed potential-flow field, runnable once `advect_vof(dt)` (rung V5a)
  exists. Basilisk's `oscillation.c` reports a few percent at comparable resolution, so the
  magnitude is not exotic; that ours does not shrink with resolution is.
- **Update (2026-09-02, WO-U E8, the collocated cross-check):** the **pressure coupling** is now
  also ruled out as the cause, and the mesh is added to the list of things that move it *without*
  explaining it. The same case on `flow.SolverColocated` (rung V8: variable density in the ABC
  approximate projection, surface tension as a face acceleration applied OUTSIDE the momentum
  solve rather than as a staggered face force inside it) reads $\omega = 0.08953$ — **−7.53 %**
  against Lamb, residual **−5.75 %** after the exact viscous shift, against the staggered
  −5.58 / −3.87 %. So the deficit survives a completely different force discretization (it is not
  a staggered-CSF artefact) but grows by ~1.9 points. The collocated grid also runs low on the
  *wave* — $\omega = 0.05975$, −0.73 % against the exact viscous root where the staggered grid
  reads −0.02 % — so the extra 2 points look like the cell-to-face average's own smoothing on both
  cases rather than a new mechanism. Its damping is 34 % below the staggered one (9.68e-4 vs
  1.47e-3). Both runs: pressure 10/500, `max|div|` 7.1e-13, volume drift −1.4e-14.

## flow: the shipped `wave` and `lamb` study gates compare against the wrong reference
- **Status:** RESOLVED (flow `f140dce`: `tests/study/vof_surface_tension.py` reports both gates against the exact viscous references of `vof_capillary_references.py`)
- **Package / area:** flow (`tests/study/vof_surface_tension.py`, gates `wave` and `lamb`)
- **Found in:** examples/capillary-oscillations — building the page is what surfaced it
- **Observed:** the `wave` gate compares the measured frequency with the **inviscid** dispersion
  relation $\omega_0^2 = \sigma k^3/(\rho_1+\rho_2)$ and the decay rate with $2\nu k^2$. Neither is
  the reference for this problem. Against them the solver reads −2.20 / −2.06 / −3.65 % in
  frequency and +182 / +380 / +78 % in decay, and the campaign spent a session hunting a
  discretization bug that was not there: against the exact two-fluid viscous root
  $s^2 + \omega_0^2(1 - k/\sqrt{k^2+s/\nu}) = 0$ the same runs are within **0.54 %** in frequency
  and 24 % in decay. $2\nu k^2$ is the *free-surface* rate; the two-fluid rate is the
  $O(\sqrt\nu)$ interfacial boundary-layer rate, 1.7–3.9× larger at these parameters. The `lamb`
  gate has the same shape of problem (inviscid Lamb only, no viscous mode), though there a real
  residual survives the correction — see the entry above.
- **Expected:** a gate quotes the reference the configuration actually has. The frequency deficit
  *growing with $\nu$* was visible in the recorded table all along and is the giveaway: no
  consistent spatial discretization error does that.
- **Repro:** `python tests/study/vof_capillary_references.py` prints both exact tables beside the
  recorded measurements.
- **Notes:** the exact references are already implemented and committed in the solver repo
  (`tests/study/vof_capillary_references.py`, `wave_mode` / `drop_mode`, the drop needs `mpmath`);
  the fix is to have the two gates import them and gate on those numbers. The page carries a
  copy of both functions, per the gallery rule that teaching code stays visible.

## flow: a flat SDF wall at a half-integer coordinate closes the wall cell's tangential faces and silently pins the contact line
- **Status:** open, reclassified: since WO-V6b the DOF classification and the openness AGREE at sdf == 0 (both wall), so the behaviour is consistent by design — a wall exactly on a cell-centre plane closes those tangential faces and pins the contact line; place a flat wall off the lattice planes when the contact line must move (VOF_PLAN §13 item 6)
  gallery page works around it by placing walls at a quarter-integer and says why)
- **Package / area:** flow (cut-cell IBM — `buildOpenness`; surfaced by the VoF contact angle)
- **Found in:** examples/droplet-wetting §6 (confirmed independently of the solver's own WO-S
  finding 5, which is where it was first measured)
- **Observed:** `buildOpenness` classifies a MAC face as fluid on `sdf > 0`, so a face whose
  sub-face SDF is exactly 0 is closed. A flat wall at $z = k + \tfrac12$ puts the *tangential*
  faces of the wall-adjacent cell exactly on the zero level, and that cell then reads a fluid
  fraction `eps = 0.500` and a tangential openness `ox = oy = 0.000` **at the same time** — a
  fluid cell with no tangential flux at all. Measured on this page (θ = 60° from a hemisphere,
  $D/\Delta = 24$, 300 steps, everything else identical): wall at $z = 4.25$ → `eps = ox = 0.75`,
  the contact line travels 90° → 73.9° and is still moving, `max|u| = 2.9e-2`; wall at
  $z = 3.50$ → `eps = 0.50`, `ox = 0.000`, the contact line stalls at 81.4° and `max|u| = 1.05`,
  a factor **36** larger. The velocity lives entirely on the closed-face DOFs, so the projection
  never sees it and the divergence, the volume drift and the pressure iteration count all look
  perfectly healthy.
- **Expected:** a wall placed anywhere inside a cell should give a cut cell whose tangential
  faces are open in proportion to the fluid it contains. `eps = 0.5` with `ox = 0` is
  geometrically inconsistent: half the cell is fluid, and none of its side is.
- **Repro:** `drop_on_wall(60.0, steps=300, zw=3.5, theta_init=90.0)` on the page, or
  `PYTHONPATH=<build> python tests/study/vof_wetting.py g1w` in the solver repo (which sweeps
  four placements).
- **Notes:** half-integer is the *natural* choice — it is what makes the wall cells "genuinely
  cut", and it is what both work orders of this rung originally asked for — so this is a trap a
  user will walk into. Candidate fixes, none implemented: treat a sub-face at exactly the zero
  level as open (`sdf >= 0`) rather than solid, which is the consistent tie-break for a face
  whose two sides are fluid and solid; or floor the tangential openness of any cell with
  `eps > 0` at some fraction of `eps`. Note also that the "wall-band spurious current" of
  ~0.79 recorded by the earlier V5a cap gate is *this*, not a surface-tension defect: the same
  measurement on a quarter-integer wall reads 1.7e-3.

## flow: `set_contact_angle` is silently ignored on a domain-BC wall
- **Status:** **RESOLVED** (flow `888733c`) — a domain wall (bc type 1 no-slip, or the new type 4
  free-slip) now carries the θ-consistent band fill: the colour block gets a SYNTHESISED
  cut-cell geometry for those faces (the out-of-domain ghost band is classified solid, and the
  wall planes are folded into the same `wallSdf` by `min`), so WO-S's θ pass runs unchanged
  with `n_w` coming out as the inward face normal. `set_contact_angle` also RAISES now when
  there is no wetting wall at all, and when a wetting domain wall has no cut-cell pressure
  operator. Byte-identical when no contact angle is set.
- **Package / area:** flow (VoF wetting — the solid-band fill runs on the SDF classification only)
- **Found in:** examples/droplet-wetting (while choosing how to model the wall)
- **Observed:** `set_domain_bc(face, 1)` gives a no-slip domain wall, but the θ-consistent band
  fill only ever runs on cells classified solid by the SDF geometry. A solver with a domain-BC
  wall and a `set_contact_angle(theta)` call therefore keeps the zero-gradient (90°) `clampFill`
  colour extrapolation on that face — no error, no warning, no diagnostic: the θ field is simply
  never consulted there. `contact_angle_diagnostics()['contact_cells']` reads 0, which is the
  only available tell and is easy to miss.
- **Expected:** either the domain wall gets the same fill with `n_w` the inward face normal
  (which is what the work order for the rung specified), or `set_contact_angle` raises / warns
  when the solver has wetting-relevant domain walls and no SDF solid.
- **Repro:** any drop resting on a type-1 domain wall with `set_contact_angle(60)`; the
  equilibrium comes back at ~90°.
- **Notes:** the workaround the page uses — and the one every gate in the solver repo uses — is
  to model a wetting wall as an **SDF slab**, which is a two-line change and costs nothing. It
  is worth documenting loudly because "a wall is a wall" is the natural expectation.

## flow: the static contact angle carries a converged −3.6° bias above 90°
- **Status:** open (published on the page as a measured limit, with the resolution rule that
  bounds it; not tuned away)
- **Package / area:** flow (VoF wetting — the θ-consistent solid-band fill / contact-line
  resolution)
- **Found in:** examples/droplet-wetting §1 and §6 (first measured in the solver's WO-S sweep)
- **Observed:** starting the drop *at* the prescribed spherical cap (so the measurement is the
  fixed-point statement, not an unfinished relaxation), $D/\Delta = 24$, Oh = 0.1, 500 steps, the
  equilibrium apparent angle comes back **30.69 / 59.98 / 88.84 / 116.86** for θ = 30/60/90/120,
  i.e. errors of **+0.69 / −0.02 / −1.16 / −3.14** degrees. The errors are monotone in θ, not
  symmetric about 90°. At density ratio 100 the same scene gives 29.92 / 58.36 / 88.44 / 116.42,
  reproducing the residual to a few tenths of a degree.
- **Expected:** ≤ 3° at every angle, which is the tolerance the rung's own gate uses and which
  the ≤ 90° rows meet comfortably.
- **Repro:** the `sweep` cell of the page, or `PYTHONPATH=<build> python
  tests/study/vof_wetting.py g1` in the solver repo.
- **Notes — what it is NOT** (each ruled out by measurement): an unfinished transient (the same
  θ = 120 scene run to 1500 steps settles at 116.40° with `max|u|` down to 1.8e-4); the density
  contrast (the ratio-100 column above); and the cut-cell whole-cell PLIC reconstruction — with
  the wall on a cell *face*, where the anchor cell is uncut and that approximation is exactly
  absent, the same run reads **worse** (115.3° at 750 steps). What it *tracks* is the contact
  radius: a = 20.2 / 15.3 / 12.1 / 9.1 cells at the four angles, and the two rows that miss are
  the two with fewer than ten radial cells across the contact line. The measurement that would
  settle it is a $D/\Delta$ refinement at fixed θ = 120/150 holding a ≥ 10, which no session has
  had the machine time for. The unimplemented refinement in the same area is the solid-clipped
  flux polygon (Chen et al., Phys. Fluids 37, 023392, 2025): the PLIC plane is reconstructed on
  the whole unit cell and its slab volume multiplied by the open face area, rather than clipped
  against the solid too.

## core/flow: a CSG leaf wider than the periodic box refills its own cavity — the ten Cate tank ran 30 % narrow → RESOLVED (detector in flow; page rebuilt)
*(found 2026-09-02 chasing the "creeping-valued confined drag" of `examples/ten-cate-sphere`)*

**Symptom.** The tank's cavity was 38 cells wide instead of 53 at d/h = 8 (d/W = 0.21 instead of
the experiment's 0.15). Every tank measurement of both campaigns — the 0.78/0.80 plateaus, the
effective K ≈ 1.67, the +24 % towed drag — was made in that narrower tank.

**Cause.** The scene query evaluates the UNION of an instance's periodic images (min over the 27
neighbours). The tank slab was `b.add_leaf("box", [NX*0.7, NY*0.7, NX*0.7])`: wider than the box,
so its images overlap and a neighbouring image's slab refills the cavity wherever it reaches
(x ∈ [14, 51] survives at N = 64). The cavity leaf is then irrelevant — 38 columns for any cavity
size. The non-periodic CSG evaluation is correct; sphere-only pages were never affected.

**Evidence.** `.sdf-campaign-probes/periodic_image_gate.py`: 0.7 L slab → 38 cols, 43 680 flagged
cells; L/2 + 1 slab → 53 cols, 0 flagged. `duct_re_gate.py` (fixed sphere, walls translating
with the plug — the exact static twin of the settling experiment): with the corrected duct the
confinement factor is K(Re 1.5) = 1.09 and K(creeping) = 1.11 relative to the periodic box, i.e.
duct Cd/Abraham 1.30 → 1.08: the solver screens confinement as the physics requires. Under the
broken slab the same gate read K = 2.35.

**Fix.** flow `set_solid_from_scene` now samples the primary image alone whenever an instance's
bounding sphere spans more than the box, counts the cells whose sign the images changed, warns on
stderr and exposes `periodic_image_overlap_cells()`. Rule for container walls: slab half-extent =
half the box + wall thickness. Page slab changed accordingly and re-measured (see the page).

**Also shipped en route.** `set_velocity(c, array)` (initial-condition hook) and the finite-Re
Galilean gate `galilean_re_gate.py`: towed vs fixed sphere agree to 0.03 % at Re 1.5 and 2.1 % at
Re 30, step by step — the moving-geometry path is Galilean-consistent at finite Re.

## flow: `vof_geometry()` throws on an all-fluid VoF solver, so one driver cannot serve both scenes
- **Status:** **RESOLVED** (flow `47d563c`) — returns the trivial geometry (eps = 1,
  openness = 1, classification 0), which is exactly what the V1 transport kernels execute, so
  `vof_geometry(0) * (1 - get_vof())` serves the packed scene and its control unchanged.
- **Package / area:** flow (VoF cut-cell diagnostics / API symmetry)
- **Found in:** examples/bubble-through-packing (the packed run and its no-packing control share
  one driver function)
- **Observed:** the natural way to write a gas-volume diagnostic for a cut-cell VoF run is
  `gas = vof_geometry(0) * (1 - get_vof())` — the cell **fluid fraction** times the gas fraction
  of that fluid volume. On a solver built with `set_pressure_geometry(all_fluid)` (the all-fluid
  cut-cell pressure operator) plus `enable_vof()`, `vof_geometry(0)` raises
  `RuntimeError: vof_geometry: no cut-cell geometry (needs set_solid + enable_vof)`. So the
  identical diagnostic code cannot be run against the packed scene and its control; the control
  branch has to synthesise `eps = ones(...)` itself.
- **Expected:** either `vof_geometry(0)` returns the all-ones cell fraction on an all-fluid
  solver (it is well defined and it is what the transport uses), or the guard is advertised in
  the docstring of `vof_geometry` next to the predicate that answers it.
- **Repro:**
  ```python
  s = flow.Solver(32, 32, 32)
  s.set_rho(1.0); s.set_mu(0.1)
  s.set_pressure_geometry(np.full((32, 32, 32), 10.0, order="F"))
  s.enable_vof()
  s.vof_geometry(0)          # RuntimeError
  s.vof_has_geometry()       # False  <- the predicate that has to guard it
  ```
- **Notes:** the workaround used on the page is
  `eps = np.asarray(s.vof_geometry(0)) if s.vof_has_geometry() else np.ones(shape)`. This is the
  same family as the `max_open_divergence()`-returns-0-without-geometry entry above: the
  cut-cell diagnostics are silently or loudly absent on an all-fluid solver, and each one has a
  different failure mode (one returns a wrong number, the other raises).

## flow: a ten-step-stale VoF `dt` re-pick is not safe in a packing — `step()` raises mid-run
- **Status:** **RESOLVED** (flow `6056e62`) — `step_adaptive(cfl_target=0.4, capillary_cfl=0.4,
  dt_max=inf)` re-picks `dt` from BOTH limits at the CURRENT state every call and returns the
  `dt` used; it reproduces the hand-written every-step loop bitwise (200 Hysing-1 steps,
  max|d dt| = 0.0, u/v/w/C/P identical), and `step()` itself is now atomic across the throw.
- **Package / area:** flow (VoF transport — the Weymouth–Yue boundedness cap and `vof_step_limits`)
- **Found in:** examples/bubble-through-packing (first attempt at the packed run)
- **Observed:** the [rising bubble](examples/rising-bubble/index.qmd) driver re-picks
  `dt = 0.4 min(cfl_dt, capillary_dt)` from `vof_step_limits()` **every ten steps**, and that is
  safe for a free bubble whose velocity field changes slowly. In a packing it is not. Deep in the
  bed the run died with

  ```
  RuntimeError: peclet::flow::vof::WyAdvector: CFL = max|uf| dt/h = 0.377061 exceeds the
  Weymouth-Yue boundedness cap 0.25 (dt = 1.27425, h = 1) - reduce dt
  ```

  `dt = 1.27425` is exactly `0.4 * capillary_dt`, i.e. at the last re-pick the capillary limit was
  binding and the CFL limit was comfortably larger; within the next ten steps the maximum face
  velocity grew by more than 50 % — a jet through a pore throat as the gas breaks into it — and
  `step()` refused. The throw happens *inside* the advection, so the step is partly applied and the
  run cannot simply be retried with a smaller `dt`.
- **Expected:** ideally `step()` would clamp to the cap it enforces (or offer an opt-in
  `set_vof_dt_autoclamp`) rather than raising after the predictor has run, so a caller cannot lose
  a two-hour run to a transient. Failing that, the limitation deserves a sentence next to
  `vof_step_limits()`: *the limits are instantaneous, and in a geometry that can accelerate the
  interface they go stale within a few steps.*
- **Repro:** the page's `column(packed=True, T=4300)` with the `dt` re-pick guarded by
  `if i % 10 == 0:` — it survives ~2 600 steps (t ≈ 2 700) and dies afterwards. With the re-pick
  every step it runs to completion.
- **Notes:** the cost of re-picking every step is one extra device reduction per step, which is
  not measurable against a variable-density projection. The page's driver also wraps `step()` in
  a `try/except RuntimeError` that records the message and stops that run cleanly, so a single
  divergent configuration cannot break the whole notebook.

## flow: the all-fluid control conserves gas volume *worse* than the cut-cell packed run
- **Status:** open (observation, not a failure — both drifts are negligible; recorded because the
  sign of the difference is the opposite of the expectation)
- **Package / area:** flow (VoF transport / cut-cell vs all-fluid pressure geometry)
- **Found in:** examples/bubble-through-packing §3 (the control and the packed run differ only in
  `set_pressure_geometry(all_fluid)` vs `set_solid(packing, cutcell_pressure=True)`)
- **Observed:** over 2 016 steps the free-rise control's gas volume drifts by **7.2e-12** relative,
  while the packed run — same fluids, same closures, same driver, 3 797 steps, and an immersed
  solid cutting the transport — drifts by **3.4e-15**, three orders *better*. It is a clean linear
  ramp in the control (visible in the page's `fig-history` right panel), not noise. Neither drift
  matches its own projected divergence: the control reports `max|div(open u)| = 6.3e-15` and the
  packed run **2.8e-14**, i.e. the run with the *smaller* divergence has the *larger* volume drift.
- **Expected:** the Weymouth–Yue budget is conditional on the velocity being discretely
  divergence-free, so the drift should scale with the projection residual and the geometry should
  make it harder, not easier.
- **Repro:** the page's `column(packed=False)` and `column(packed=True)`; the numbers are the
  `V/V0 - 1` column of its summary table.
- **Notes — candidate explanations, none checked:** (a) the two runs use different conserved
  functionals in the *diagnostic*: the packed run weights by the solver's cell fluid fraction
  `vof_geometry(0)`, the control by ones (because `vof_geometry` raises on an all-fluid solver —
  see the entry above), so the control's sum is over a slightly different set of cells than the
  solver's own `eps_eff = max(eps, 1/64)` functional; (b) the control's bubble spends the run
  crossing a domain with no cut cells at all, where the `eps_eff` floor never engages; (c) simple
  step-count and path-length differences. Worth ten minutes with `vof_diagnostics()['volume']`
  (the solver's own conserved quantity) instead of a hand-rolled sum on both runs — that would
  separate a *diagnostic* artefact from a *transport* one, and (a) predicts it is the former.
## `step()` is not atomic across the Weymouth–Yue boundedness throw: the momentum half has already advanced
- **Status:** **RESOLVED** (flow `7c5c066`, branch `vof-issues`) — the Weymouth–Yue boundedness
  cap and the Brackbill capillary cap are now evaluated at the HEAD of `step()`, before the
  first mutator, so a throw leaves `get_u/get_v/get_w/get_vof/get_p` bitwise as they were and a
  retry at a smaller `dt` is exact (gate: the reproducer below, all five max|d| = 0.0). One
  limit is stated rather than hidden: without `enable_vof_momentum` the advection sits at the
  TAIL of the step, so the pre-check reads the field the call STARTS from and cannot see the
  projection accelerating it inside the step — which is what the new `step_adaptive()` removes.
- **Package / area:** flow (VoF transport / time-step control)
- **Found in:** examples/trickle-flow-packing (a liquid jet impinging on a packing)
- **Observed:** `IbmSolver::step()` advances momentum and the projection first and the colour
  advection second. When the colour advection rejects the step —
  `WyAdvector: CFL = max|uf| dt/h = 0.257 exceeds the Weymouth-Yue boundedness cap 0.25` — the
  throw leaves the **colour field untouched and correct** (verified: `sum C` and `min/max C`
  unchanged, and a retry at a smaller `dt` runs), but the **velocity field has already been
  advanced by the rejected `dt`**: with a body force `g_z = 1e-3` and the rejected `dt = 0.4`,
  `max|w|` changes by exactly `4.0e-4 = g_z dt` across the throwing call. So the obvious driver
  pattern — catch the exception, halve `dt`, call `step()` again — silently gives the momentum
  equation one extra over-long step that the colour never sees, i.e. it desynchronises the two
  fields rather than retrying the step.
- **Expected:** either `step()` is atomic (nothing is committed if the colour advection will
  reject the step — the CFL is computable from the projected face field *before* the colour
  advection, so the check can be hoisted), or the exception documents that the solver state is
  half-advanced and a retry is invalid.
- **Repro:**
  ```python
  n = 16
  s = flow.Solver(n, n, n); s.set_rho(1.0); s.set_mu(0.01); s.set_dt(0.1)
  s.set_pressure_geometry(np.full((n, n, n), 1e30, order="F"))
  s.set_body_force(0.0, 0.0, 1e-3); s.enable_vof()
  C = np.zeros((n, n, n), order="F"); C[:, :, : n // 2] = 1.0; s.set_vof(C)
  u = np.zeros((n, n, n), order="F"); u[:] = 1.0; s.set_field("u", u)
  for _ in range(3): s.step()
  w0 = s.get_w().copy()
  s.set_dt(0.4)                       # CFL 0.4 > the 0.25 cap
  try: s.step()
  except RuntimeError: pass
  print(np.abs(s.get_w() - w0).max())  # 4.0e-4 = g_z * dt : the momentum half ran
  ```
- **Notes:** the workaround this page uses is to make the throw unreachable — re-pick `dt` from
  `vof_step_limits()["cfl_dt"]` **every** step rather than every 10 steps. Every-10 is what the
  solver's own `tests/study` scripts do and it is enough for a film or a rising bubble; it is not
  enough for a jet impinging on a packing, where `max|u_f|` can double inside ten steps (measured:
  the limit fell from `cfl_dt = 1.64` to `0.30` over roughly 100 steps and then dropped below the
  stale `dt` within ten).
## flow: an SDF wall on an INTEGER coordinate (exactly on a cell face) makes a driven two-phase run diverge geometrically
- **Status:** **RESOLVED** (flow `fa1e346`, `src/mac_ibm.hpp`) — root-caused to a tie-break
  disagreement at `sdf == 0` and fixed; the page's `doublet-wall-probe` cell re-runs the
  integer-wall scene on the fixed build and it is stable. The *half*-integer case below is not
  fixed and remains a scene rule.
- **Package / area:** flow (cut-cell VoF + static contact angle on a flat SDF wall)
- **Found in:** examples/pore-scale-imbibition (the pore doublet; WO-V7 case 1)
- **Observed:** the doublet's three solid slabs are boxes. With their faces at integer $z$ —
  i.e. exactly on a cell face, so `sdf` at every cell centre is $\pm\tfrac12$ and **no wall cell is
  cut at all** — the corner where a channel mouth meets the slab front reads

  ```
  step  1  max|u| 1.125e+02      (physical scale: U * NZ/(w1+w2) = 0.42)
  step 50  max|u| 1.106e+03  dt 1.9e-04
  step300  max|u| 1.522e+08  dt 1.4e-09
  ```

  i.e. the velocity grows by about 5 % *per step* while the interface-local `dt` limiter chases it
  down by the same factor, so the Weymouth–Yue cap never fires and the run never raises — it just
  stops advancing in time (`t` frozen at 0.187 s after 1 381 steps) and reports
  `max|div(open u)|` of $2\times10^{20}$ with the pressure solve reporting a healthy 30 iterations
  out of 400 throughout. **Nothing in the run's own diagnostics says "invalid" except the clock.**
- **The same scene with every wall shifted by 0.25 of a cell** (nothing else changed): step 1
  `max|u| = 3.56`, *decaying* to 1.2 by step 12, `dt` at the capillary limit, and the run completes.
  Shown not to be the contact angle (a neutral 90° fill diverges identically), not the density
  ratio (ratio 1 diverges more slowly), not surface tension (the first-step velocity is already
  $1.1\times10^2$ with $\sigma$ off) and not the corners (a plain slit with no septum diverges the
  same way). Removing the solid entirely and keeping everything else — inflow, outflow, ratio 100,
  momentum consistency, surface tension — is perfectly stable at `max|u| = 0.277`.
- **Expected:** either the wall-cell openness/`eps` construction should be robust to the
  wall-on-a-face degenerate case, or `set_solid` should *warn* when a flat SDF interface lands
  within a small tolerance of a cell face while VoF is enabled. A silent geometric divergence
  whose only tell is that simulated time stops advancing is the worst available failure mode.
- **Repro:** `flow/tests/study/pore_scale/pore_doublet.py` with `WALL_SHIFT = 0.0`.
- **Root cause and fix.** Not the cell fraction — the *velocity DOF*. The staggered SDF sample is
  the mean of the two adjacent cell-centre values, so a wall on an integer coordinate puts the
  normal component's DOF at `sdf == 0.0` exactly, in IEEE. Five consumers classify a DOF from that
  sample and one of them disagreed: `ibmSolidMask` (which pins a DOF to the wall datum) used
  `sd < 0` and so called it **fluid**, while `ibmIsCut` (which decides whether a wall closure is
  built), `ibmCleanFluidMask` and the two face-openness predicates all use `<= 0` and called it
  **non-fluid**. The DOF was therefore neither pinned nor closed nor given a Dirichlet datum, its
  face was closed to the projection so the pressure solve never saw it, and it was still read by
  its neighbours' advection and diffusion stencils: an unconstrained unknown sitting on the wall.
  `ibmSolidMask` now uses `sd <= 0`. The change is inert wherever no DOF sample is exactly zero
  (32 of 33 `tests/kokkos` binaries byte-identical), and the one test it moves — `test_vof_cutcell`,
  whose G5 scene puts a wall on a cell-centre plane — improves on every metric it prints
  (wall-band `max|u|` 7.9e-01 -> 5.1e-03, volume drift 5.9e-16 -> 0).
- **What is NOT fixed.** A wall on a **half**-integer coordinate (a cell-centre plane) puts the two
  *tangential* DOFs exactly on the wall, and they are now pinned to the wall datum — so no wall
  model, including the Navier slip, can act there and a contact line on such a wall is
  structurally pinned. **Quarter-integer placement remains the scene rule**, now for the wetting
  reason rather than the stability one.
- **Notes:** the driver-side guard is still worth having and is still missing: a run whose `dt`
  falls orders below its initial capillary limit while `t` stops advancing is diverging, and
  nothing in `flow` says so. This fix removes the cause this entry found, not the class.

## flow: `vof_step_limits()['capillary_dt']` is a function of the CURRENT density field, so the first dt of a gas-filled domain is 7x too large
- **Status:** **RESOLVED** (flow `6056e62`) — same fix: `step_adaptive()` evaluates
  `capillary_dt` from the state as it stands at the call, so a driver never sizes a step from a
  pre-closure value. The state-dependence itself is real and is now documented on the entry
  point rather than left for the user to discover.
- **Package / area:** flow (VoF, the Brackbill capillary step limit)
- **Found in:** examples/pore-scale-imbibition (all three cases start gas-filled)
- **Observed:** `capillary_dt` evaluates $\sqrt{(\rho_1+\rho_2)h^3/4\pi\sigma}$ from the density
  field as it stands. Immediately after `enable_vof` on a domain that is entirely gas, the field
  has not been updated by the closures yet and the call returns the *base* `set_rho` value
  (0.2835 s here); one `step()` later the field is all gas and it returns 0.0399 s — a factor of
  7.1 smaller. A driver that sizes its first `dt` from the pre-step call therefore starts 7x over
  the stability limit and the advector throws on step 1:
  ```
  RuntimeError: surface tension: dt = 0.141700 exceeds the capillary limit 0.019947
  ```
- **Expected:** a sentence in the `capillary_dt` / `vof_step_limits` docstrings saying the value
  is state-dependent and is only meaningful *after* the property closures have run once — or have
  `enable_vof`/`set_property_model` refresh the properties so the first call is already right.

## flow: a two-phase post array with 3-cell throats dies with `preconditioner produced non-finite z`
- **Status:** **RESOLVED as a VISIBILITY defect** (flow `89ea438`); the underlying 3-cell-throat
  mechanism is still not isolated and the entry stays open for that. A solve that gives up on a
  non-finite preconditioner output now sets `pressure_solve_failed()` and reports the iteration
  CAP through `last_pressure_iterations()`, so the usual rule-3b check catches it;
  `PECLET_FLOW_PRESSURE_STRICT=1` raises instead. `micromodel_2d.py --reproduce-wov7` rebuilds
  the original 56-post array and its `Health` tracker counts the breakdowns.
- **Package / area:** flow (cut-cell VoF + contact angle in an under-resolved throat; the FCG
  pressure driver's preconditioner is where it surfaces)
- **Found in:** examples/pore-scale-imbibition (the micromodel; WO-V7 case 3)
- **Observed:** a jittered staggered array of 56 posts of radius 5.7 at porosity 0.586 in
  $128\times128\times4$ — narrowest throat **3.08 cells** — invaded at $\theta=45°$,
  $\mathrm{Ca}=10^{-3}$, ratio 100, momentum consistency on. It ran to 0.121 pore volumes injected
  with $\max|u|$ climbing from 0.40 to 2.32 (93x the 0.025 inlet velocity) and then emitted, four
  times in a row,

  ```
  peclet::flow CutcellMG::solveFCG: preconditioner produced non-finite z; returning zero correction
  ```

  The same scene with **30 posts of radius 6.5, narrowest throat 6.4 cells, porosity 0.712** and
  every other setting identical runs on.
- **Two candidate mechanisms, not separated:** (a) the $\theta$-fill writes a three-cell band into
  the solid on each side of a throat, so at 3.1 cells the two posts' bands meet in its middle —
  the same overlap the wetting rung recorded as making its four-cell-plate capillary rise
  inconclusive; (b) a Haines jump through a throat whose meniscus radius is ~1.5 cells is simply
  unresolved (local velocities in a real pore-filling event run up towards $\sigma/\mu_\ell$,
  which is 1000x the inlet velocity here). Separating them needs a $\theta$-sweep at fixed throat
  width.
- **Expected:** whatever the mechanism, the *failure mode* is wrong: the message is printed to
  stdout, the correction is silently replaced by zero, and the run continues. A non-finite
  preconditioner output should mark the step invalid — `last_pressure_iterations()` should report
  the cap, or the driver should raise — so that a caller's rule-3b check catches it. As shipped, a
  run can pass "no capped solve" while its pressure solve has been returning zero corrections.
- **Repro:** `flow/tests/study/pore_scale/micromodel_2d.py` with `NCOL, NROW = 7, 8`,
  `X0, DX = 16.0, 16.0`, `R_POST = 5.7`, `MIN_GAP = 3.0`.

## flow: contact-line mobility is set by the wetting band, and neither the angle model nor the wall slip length reaches it
- **Status:** open (measured and bounded, not worked around — the affected results on the page are
  labelled qualitative rather than tuned)
- **Package / area:** flow (VoF wetting: the θ-fill band, `set_contact_angle`,
  `set_contact_angle_dynamic`, `set_wall_slip_length`)
- **Found in:** examples/pore-scale-imbibition §1 (the Navier-slip control), and independently in
  all three of the page's cases
- **Observed:** every case on the page whose published expectation depends on a *wetting* front
  advancing under its own capillary suction either gets the **sign** wrong or shows no dependence
  at all. Measured, on the fixed CUDA build at flow `a16d9a1`:
  - **pore doublet** (88x4x80, θ = 45°, Ca = 1e-2/1e-3/1e-4): Chatzis–Dullien predicts narrow-first
    at all three; measured narrow-first only at Ca = 1e-2 (68.4 s against 74.6 s) and wide-first at
    1e-3 (921.4 s against 453.6 s) and 1e-4. The *drainage* column is fine — at θ = 135°,
    Ca = 1e-3 the narrow branch ends at S = 0.004 against the wide branch's 0.912.
  - **sphere packing** (48x48x96, Ca = 1e-3): breakthrough at 800.5 s / S = 0.826 for θ = 30° and
    809.1 s / S = 0.835 for θ = 60° — **1 % apart in both**, against a factor-of-two change in
    cos θ and a large predicted difference. The trapped gas agrees to three digits (0.012 / 0.011).
  - **micromodel** (128x128x4, θ = 45/90/135° at a common 0.10 PV injected): front roughness
    5.06 / 5.11 / 4.55 cells, deepest finger 18 / 17 / 15, box dimension 1.624 / 1.605 / 1.636 —
    **not ordered in θ**, every angle reaching every transverse row as one connected cluster. The
    published compact-to-fingered transition is absent; what little spread there is has the
    *wetting* case as the rougher one, i.e. the inverted sign.

  The obvious cause is the wall's momentum condition, and the page tests it directly:
  `set_wall_slip_length(λ)` for λ = 0, 0.1 and 0.5 cells on the doublet at $\mathrm{Ca}=10^{-3}$,
  $\theta=45°$ leaves the ordering unchanged (the wide branch wins in every row; the narrow
  branch's breakthrough moves 1.5 %, 921.4 -> 907.2 s, the wide branch's 3 %). The companion
  measurement on a quantitative benchmark is sharper: on capillary rise between two plates the explicit slip buys **+26 %** of
  the Lucas–Washburn rate at λ = 0.3 and leaves it **175×** too slow, and **doubling the slot
  width makes the rise 2.5× *slower*** where the law requires it to be 2× faster — i.e. the front
  speed goes as $1/w$, the capillary drive $2\sigma\cos\theta/w$ divided by a resistance that does
  not scale with the gap at all. At both gap widths the interface's own apparent angle sits at
  ≈71° while the imposed angle is ≈37°.
- **Expected:** with a static or a Cox–Voinov angle imposed and a Navier slip length λ set, the
  contact-line speed should be controlled by (θ, λ) and the rise should obey Lucas–Washburn to
  within the usual O(1) factor.
- **Mechanism (named, not fully isolated):** the limiter is *local to the few-cell wetting band* —
  the colour's motion through the near-wall cells and the curvature that band produces — and is
  independent of the confinement. It is what caps the delivered Young force at
  $\cos(71°)/\cos(37°) \approx 0.4$ of the intended one. Neither the imposed angle nor the wall
  velocity closure controls it; both are exact on their own unit tests.
- **Repro:** `flow/tests/study/pore_scale/pore_doublet.py --theta 45 --ca 1e-3 --slip 0,0.1,0.5`
  for the ordering, and `flow/tests/study/vof_wetting_dynamic.py lw` for the rate and the
  gap-width probe.
- **Notes:** the practical consequence for a user, and the reason this is logged rather than
  tuned: **drainage** ($\theta > 90°$) results in this scheme are quantitative, and **imbibition**
  ($\theta < 90°$) results are qualitative — the *contrast* between a wetting and a non-wetting
  fluid at a fixed capillary number is real and large (a factor of 200 in the doublet's narrow
  branch), while the *dependence on how strongly wetting* the liquid is, which is what the packing
  and the micromodel test, is not delivered at all.
