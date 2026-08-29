# PLAN — SDF-showcase examples & benchmarks (executable spec, hand to Opus)

> Status: PLAN, written 2026-08-30 by the SDF-campaign agent at the user's request. The analytic-SDF
> campaign is complete (suite/docs/ANALYTIC_SDF_GEOMETRY.md, status banner + §6.5); these examples
> are its public showcase. Each example follows STYLE_GUIDE.md (self-contained `examples/<slug>/
> index.qmd`, teaching code visible, plumbing in `src/peclet_examples/`), gets a QUANTITATIVE gate
> against literature or an exact solution wherever one exists, and is frozen + committed + pushed
> individually. Lessons from PROGRESS.md apply: these are mostly **GPU examples** (the BFS/vortex-
> street CPU lesson); render against a CUDA build via `PECLET_LOCAL_BUILD`.

## What the examples collectively showcase (the new capabilities)

`peclet.core.geom` Python authoring (SceneBuilder: leaves + CSG + quaternion transforms +
instancing), `body_properties` (mass/COM/inertia → principal moments + quaternion, implicit
quadrature, no bound-leaf bias), `principal_frame` (exact reframe), dem `SHAPE_SCENE` (composed
analytic trees as colliding particles, analytic ridge-exact contact normals via `evalTreeGrad`),
flow moving geometry (Layer 3: instance velocities, wall flux, `rebuild_geometry`), the resolved
CFD-DEM loop with the **discrete-reaction force** (route b, exactly conservative), analytic walls
with rigid-body velocity, and quadrature apertures. Suite-side gaps that examples need are Phase-0
rungs below — do them in the SUITE first, gated and committed there, before the example that
depends on them.

---

## Phase 0 — suite-side prerequisite rungs (each its own gated suite commit)

- **R0 — advective term in the reaction budget** (needed by ten-cate E2–E4 and DKT; flow).
  `hydro_force_torque_reaction` v1 refuses `advect_`. Extension: stash the per-cell advective RHS
  contribution the LAST Picard iteration actually used (the `−rho*aK (+rho*aF)` term of buildRhs —
  cleanest as a `deep_copy` of a dedicated field written inside buildRhs when `hasScene_`, exactly
  like `uStar_`), and subtract it in `R_i`. The implicit-FOU path modifies A instead — refuse
  `implicitAdv()` in v2 too (explicit SOU/Koren only). *Gate:* the momentum-balance identity
  ΣF = f·N_fluid at a steady driven bed **with advection on** at Re ~ 30, to solver residual
  (the route-b criterion: percent-level = missing term); plus the settling gate unchanged.
- **R1 — rotating analytic-wall geometry** (needed by the stirrer E5; dem).
  Walls already carry rigid-body SURFACE velocity (`set_wall_velocity`, v = linVel + angVel×(r−c))
  — enough for a drum (axisymmetric) but a stirrer blade's GEOMETRY must rotate. Add
  `set_wall_transform(wall_index, translation, quat)`: recompose the wall tree's root transform
  (`SceneBuilder::composeTransform` is in core) and re-upload the KB-sized `wallNodes` View.
  Keep `set_wall_velocity` the source of the surface velocity; the example drives both
  consistently per step (transform ← integrate angVel). *Gate:* a wall rotated by θ and a wall
  AUTHORED at θ give bitwise-identical `sampleWallSdf` on a probe battery; a slowly rotated drum
  reproduces the static-drum trajectory at OMP_NUM_THREADS=1.
- **R2 — external torques in dem** (needed by Jeffery E8, and completes §7 item 5; dem).
  `set_external_torques((N,3))`: body-frame? NO — accept WORLD-frame torque, rotate into body
  frame in the predictor where the gyroscopic term already lives (`dw = invI·(τ_body − ω×(Iω))·dt`
  — the ω×Iω part is already there). Wire `ResolvedCfdDem` to hand the reaction torque over.
  *Gate:* a single particle under constant world torque about a principal axis spins up at
  τ/I·t exactly; under torque about a NON-principal axis matches a scipy Euler-equation reference.

---

## Phase 1 — no prerequisites (start immediately, any order)

### E1. `tennis-racket` — the Dzhanibekov / intermediate-axis effect  ★ the inertia showcase
Physics: torque-free rotation about the middle principal axis is unstable; a racket spun about it
flips by half-turns with a well-defined period. Analytic reference: torque-free Euler equations
(Landau–Lifshitz *Mechanics* §37; Jacobi elliptic functions) — in practice integrate them with
`scipy.solve_ivp` at machine precision as the reference, and quote the elliptic-period formula.
- Build: SceneBuilder racket = torus head (certified leaf) ∪ two short capsule throat arms ∪
  capsule handle; `body_properties` (must show three DISTINCT principal moments — print them and
  the quaternion); `principal_frame`. dem: ONE particle, no gravity, no contacts, shape registered
  via `scene_particle` (movie geometry = the bake's marching-cubes mesh, transformed per frame by
  the particle quaternion). Initial ω = intermediate axis + 1e-3 perturbation.
- dem's predictor already carries the gyroscopic ω×(Iω) term (`integration.hpp`) — **no solver
  change**; this example is a pure test of the inertia pipeline feeding it.
- Gates: (i) simulated flip period vs the Euler-ODE reference using the MEASURED I1<I2<I3, within
  a stated % (do a dt-convergence ladder; dem state is float32 — measure the drift, report it);
  (ii) |L| and rotational energy drift over 10 flips (report); (iii) stability contrast: spins
  about the major and minor axes do NOT flip. Movie: the flipping racket, colored faces.
- Trap: quaternion renormalization cadence in dem may set the energy-drift floor — measure first,
  claim after.

### E2. `oscillating-sphere` — unsteady Stokes drag vs Stokes (1851)  ★ the moving-wall + reaction showcase
Physics: sphere oscillating at velocity Û e^{−iωt} in unbounded viscous fluid; exact drag
F̂ = 6πμR Û (1 + λR + (λR)²/9), λ² = −iω/ν, Re(λ) > 0 (Stokes 1851; Landau–Lifshitz *Fluid
Mechanics* §24; Kim & Karrila) — in-phase (enhanced drag) and out-of-phase (added mass + history)
parts as functions of δ/R, δ = √(2ν/ω).
- KEY IMPLEMENTATION INSIGHT: the theory is the LINEARIZED problem (amplitude A/R → 0), where the
  BC is applied at the mean position — so the geometry NEVER MOVES. Static sphere instance +
  sinusoidal `set_instance_motion(lin_vel=[U(t),0,0])` each step + NO rebuild_geometry: no fresh
  cells, no rebuild cost, advection off (rigorously valid in this limit), the reaction budget's
  time term does the unsteady work. One translating-with-rebuild run at small A/R as a cross-check
  that the two agree.
- Force: Fourier-fit `hydro_force_torque_reaction` F_x(t) over ≥5 settled cycles → complex F̂.
- Periodic-image handling: the potential (added-mass) part decays 1/r³, the steady-limit viscous
  part 1/r — use the settling-gate trick: CALIBRATE the box (measure the steady drag λ_box in the
  same box) and normalize, and/or sweep L/R; report both raw and corrected. Resolution constraint:
  δ ≥ 4h sets ω_max per grid; sweep δ/R ∈ [0.5, 3] across N ∈ {64, 96, 128}.
- Gates: Re/Im(F̂)/(6πμRÛ) vs the closed form across the sweep, error table + convergence; the
  δ→∞ limit must recover the calibrated steady Stokes drag.

### E4a. `pall-ring-packing` (part 1: the dem pack)  ★ the composed-particle showcase
Author a Pall-ring-like particle: **design it for prunability** — a CSG *difference* keeps the
LEFT child's certificate, so build ring = difference(hollow_cylinder [certified, distance-exact],
union of window boxes), plus two inner web boxes; `principal_frame`; `scene_particle.build`.
dem packs ~30–60 rings into a periodic box (or small cylinder with an analytic wall) under
gravity + shaking, OMP_NUM_THREADS as needed (packing is not a determinism claim). Deliverables:
porosity vs literature packing porosity for Pall rings (ε ≈ 0.9-ish for real 1-inch rings — ours
are thick-walled minis; report ours honestly vs geometry), contact/orientation statistics, movie
of the pour. Freeze the final state (positions + quaternions) as the input to E4b.
- Traps: `set_positions` resets shape ids (re-apply after); shell decimation sets contact
  resolution — pick shell_resolution so probe spacing ≲ min feature (web thickness)/3.

### E7 (small). `nonsphere-drag` — cube & superquadric drag correction factors
Stokes drag of a cube / rounded superquadric vs Haider–Levenspiel (1989) / Leith (1987)
sphericity correlations, using the calibrated-box method (measure the sphere in the SAME box,
report K = F_shape/F_sphere at equal volume — box corrections cancel to leading order). Cheap,
quantitative, exercises superquadric + box leaves and the reaction force. Half a day.

---

## Phase 2 — after Phase-0 rungs

### E3a. `ten-cate-sphere` — settling sphere vs PIV (needs R0 for E2–E4 cases)
ten Cate, Nieuwstadt, Derksen & Van den Akker, *Phys. Fluids* 14, 4012 (2002): a single sphere
(d = 15 mm) settling in a closed 100×100×160 mm silicon-oil tank; four cases E1–E4 with
Re_max ≈ 1.5, 4.1, 11.6, 31.9; the paper gives u(t) trajectories (PIV) that every resolved-
particle code validates against.
- Container: the TANK IS A STATIC SCENE INSTANCE (an inverted box: difference of a slab and the
  cavity), so flow's moving-geometry v1 scope (no domain BCs) is respected — the periodic domain
  just wraps solid. Sphere: second instance, `ResolvedCfdDem` with gravity, reaction force.
  Ship E1 first (quasi-Stokes, advection off — TODAY's scope), then E2–E4 with R0.
- Gates: u(t) overlay vs digitized experimental curves (put the digitized CSVs in `literature/`),
  peak settling velocity within the few-% band published resolved codes achieve; grid ladder
  (d/h ∈ {8, 12, 16, 24}); wall-touchdown behavior reported, not overclaimed (lubrication is
  unresolved; dem contact takes over — say so).

### E4b. `pall-ring-flow` (part 2: flow through the pack)
Hand E4a's frozen pack to flow ANALYTICALLY: same trees, per-particle transforms from dem state
(the ResolvedCfdDem bridge, static) → `set_solid_from_scene`. Pressure drop vs superficial
velocity across 3–4 flow rates; compare against the Ergun equation and a Pall-ring correlation
(Stichlmair / Billet–Schultes dry-ΔP), plotted as a band and honestly labeled (small periodic
sample, no column walls, thick-walled mini-rings — expect correlation-band, not %-agreement).
Visuals: streamlines threading ring windows, pressure field slice. Cost note: certified-difference
rings prune (that was the E4a design decision paying off) — measure and report set_solid time.

### E5. `stirred-column` — dem mixing with a rotating stirrer (needs R1)
Cylindrical column (inverted solid cylinder analytic wall) + pitched-blade stirrer (SceneBuilder:
shaft capsule ∪ 2–4 rotated blade boxes) as an analytic WALL, rotated each step via R1's
`set_wall_transform` + matching `set_wall_velocity`. ~20–50k spheres colored by initial layer
(bottom/top halves or quadrants). Deliverables: the mixing movie (the point of the example);
Lacey mixing index M(t) vs impeller revolutions on a fixed spatial binning; velocity field /
recirculation pattern compared QUALITATIVELY with published bladed-mixer DEM (e.g. Remy, Khinast
& Glasser, AIChE J. 2009) — claim the pattern, not numbers. OMP single-thread only for any
before/after numeric check; the showcase run may be multithreaded/CUDA (say which).

---

## Phase 3 — stretch (order by appetite)

### E3b. `drafting-kissing-tumbling` (needs R0)
Two spheres released in-line (Fortes, Joseph & Lundgren, *JFM* 177, 1987): draft → kiss → tumble.
Compare against a published 3-D reference trajectory (Glowinski et al., *JCP* 169, 2001 §9, or
Breugem 2012) — gap-vs-time and the tumbling onset. The selling point: the kiss is handled by
REAL dem contact inside the resolved loop. Sensitivity to initial offset is genuine physics —
present phases + timings, not chaos-sensitive exactness.

### E8. `jeffery-orbit` (needs R2) — flagship-grade if it fits
Prolate ellipsoid (bound leaf!) in Couette: two parallel analytic wall-plates as STATIC instances
carrying opposite `lin_vel` (moving-geometry v1 compatible: velocity without translation, no
rebuild). Reaction TORQUE → dem via R2. Gate: orbit period T = (2π/γ̇)(r + 1/r), Jeffery (1922),
across aspect ratios r ∈ {2, 4} — an EXACT analytic target for the full resolved rotational loop.

### E9 (small). `dumbbell-sedimentation`
A fused bi-sphere settles broadside-on at low Re; terminal velocity vs the exact two-sphere
mobility results (Goldman–Cox–Brenner lineage / Kim & Karrila tables). Cheap, quantitative,
uses a composed particle in the resolved loop with rotation (needs R2 for the torque to
reorient it — else document the fixed-orientation variant).

---

## Standing traps for the executor (each cost real time in the campaign; do not re-learn)
1. dem numeric comparisons ONLY at OMP_NUM_THREADS=1; `set_positions` RESETS shape ids — reassign
   after; `dem.step()` without dt advances nothing; dem assigns unit mass — set physical inertia.
2. flow on GPU: `set_pressure_multigrid(levels=1)` is a 50× tax (920 vs 19.5 ms/step at N=64) —
   use depth ≥ 4. Compare staggered fields at staggered points. A/B cost runs need a body force
   (a zero-RHS baseline "solves" nothing).
3. Reaction-force scope guards throw loudly — that is the design; extend the budget (R0), never
   bypass the guard. The momentum-balance identity is the completeness check: solver-residual
   good, percent bad.
4. Drag vs literature in a periodic/finite box: calibrate IN THE SAME BOX (the settling-gate
   pattern) so image/blockage corrections cancel; and check δ or wake scales fit the box.
5. Every example self-contained per STYLE_GUIDE.md; digitized literature data as small CSVs in
   `literature/` with provenance in `references.bib`; log dead ends to ISSUES.md.

---

## OPEN FOR REVIEW (raised while executing this plan, 2026-08-30)

Things the plan did not resolve that materially change numerics or the API. The conservative option
was taken in each case and is stated; none is settled.

1. **The reaction-force gate's wording, after R0.** The plan asks for "the momentum-balance identity
   ΣF = f·N_fluid … with advection on … to solver residual". Implementing R0 showed that form is
   *not* the identity once advection is on: the full discrete statement is

       Σ_bodies F = f·N_fluid + Σ fb + Σ_i A_i − Σ_i (ρ/dt)(u_i − uⁿ_i)

   and `Σ_i A_i` — the advection operator's own net momentum flux through the cut walls — is nonzero
   (**−0.965% of f·N at N=32, −0.369% at N=48**, converging like O(h^2.4)). With it carried, the
   budget closes to **−6.8e-15 / −3.7e-15**, i.e. round-off, which is what the gate actually wanted
   to establish. Conservative option taken: **report** `Σ A` through a new
   `reaction_budget_terms()` and state the identity in full, rather than absorb it (which would turn
   a solver property into an invisible force bias) or change the advection stencil at cut cells
   (which would perturb every validated result resting on the momentum operator). Written up as
   §7 item 8 of `suite/docs/ANALYTIC_SDF_GEOMETRY.md`.

2. **E2's "the geometry never moves, so there is no rebuild cost" is wrong as the API stands.**
   `set_instance_motion` uploads the instance velocities, but the wall-velocity fields (`uBc_`,
   `uwCell_`) and the momentum operator's inhomogeneous term are built inside
   `set_solid_from_scene` — so a time-varying wall velocity has **no effect at all** until the
   geometry is rebuilt. Conservative option taken: call `rebuild_geometry()` every step (correct;
   the transforms are unchanged so the geometry is re-derived identically, and u/P are preserved),
   at roughly 3× the cost of a plain step. The cheap fix, if this becomes a pattern, is a
   `refresh_wall_velocity()` entry point that runs `buildWallVelocity()` + `rebuildStencils()`
   without re-sampling the SDF — a small, well-factored addition, deliberately NOT made here
   because it is a solver API change outside the Phase-0 rungs the plan authorises.

3. **E2's box-calibration prescription is wrong at finite frequency.** The plan says to "CALIBRATE
   the box (measure the steady drag λ_box in the same box) and normalize". Measured, that
   *over*-corrects badly: the steady Stokeslet is long-ranged (1/r), so the steady periodic
   correction is large (λ_box = 1.710 at φ = 0.0141, against Hasimoto's 1.700 for a simple-cubic
   array — 0.56%, an independent check of the calibration itself), whereas the **oscillatory**
   Stokeslet decays like e^{−r/δ}/r and its images are exponentially screened, ~e^{−L/δ} = 1.3e-03
   at δ/R = 1 in an L/R = 6.7 box. Dividing by λ_box therefore removes a correction that is not
   there. Conservative option taken: report the **raw** coefficient against Stokes (1851) together
   with an explicit error budget — screened viscous images e^{−L/δ}, potential-part images (R/L)³,
   the unscreened k=0 momentum mode O(φ), and discretisation O(h²) — and separate them with a grid
   ladder at fixed L/R.

4. **A uniform body force used to pin the mean flow is not free.** The first E2 driver pinned
   ⟨u⟩ = 0 with a per-step uniform body force (the settling-gate pattern). It works — ⟨u⟩ held to
   3.8e-10 of U₀ — but the force it applies exerts a generalised-buoyancy force on the body that the
   unbounded theory does not contain, measured at ~8% of the drag at δ/R = 1. Conservative option
   taken: **do not pin the mean** in the oscillating case; let it oscillate (it is set by momentum
   conservation, with no mean pressure gradient in a periodic box) and quantify its residual effect
   as part of the error budget above. The steady calibration keeps the classic fixed-body,
   body-force-driven form, where the same objection does not arise.
