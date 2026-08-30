# Overnight build progress

## SDF-SHOWCASE CAMPAIGN (2026-08-30, in progress) — `PLAN_SDF_SHOWCASE.md`

Legend: [x] done+pushed · [~] in progress · [ ] todo · [!] blocked/documented

### Phase 0 — suite-side rungs (all landed and pushed, submodules then umbrella)
- [x] **R0** flow: explicit advection in the reaction budget (`flow f61dfaa`). Gate: the identity
      closes to **−6.8e-15 (N=32) / −3.7e-15 (N=48)** at Re_d = 23.3 with advection on; settling
      gate unchanged at slip ratio **0.9989**; flow fingerprint `u_sum 6.74193610583927948e+05`
      bit-identical at 4 threads. Exposed a *solver* property, not a budget gap — the advection
      operator's cut-wall momentum flux, **−0.965% of f·N at N=32, −0.369% at N=48** — now reported
      through a new `reaction_budget_terms()`. See OPEN FOR REVIEW 1 in the plan.
- [x] **R1** dem: `set_wall_transform` + `wall_sdf_at` (`dem d820f23`). Gate: placed-vs-authored wall
      SDF **bitwise identical** over 4000 probes; absolute (100 identical calls bitwise stable) and
      returns home bitwise; a barrel's self-axis rotation moves its SDF by **2.4e-06** (the float32
      floor) and a drum bed's bulk COM by **6.1e-05 grain radii**; the per-grain spread is bounded
      by a rotated-vs-rotated control.
- [x] **R2** dem: `set_external_torques` (same commit). Gate: principal-axis spin-up exact to dem's
      float32 floor (**1.8e-05 … 3.4e-05** at 4000 steps, growing with step count); non-principal
      axis vs a scipy DOP853 Euler-equation reference **4.9e-04 at dt=1e-3, order 0.94–1.00**;
      `L_world(t) − L_world(0) = τt` to **3.0e-04 … 9.3e-04**. dem 8/8 kernel + 24/24 MPI ctests.
- [x] umbrella bumped + `docs/ANALYTIC_SDF_GEOMETRY.md` updated (`peclet 6371a73`): Layer 3 rung 5,
      §7 item 1 → v2 scope, §7 item 5 RESOLVED, new §7 item 8.

### Phase 1 — examples with no prerequisites
- [x] **E1 `tennis-racket`** — the Dzhanibekov flip from an analytic CSG particle. First flip within
      **0.020%** of the torque-free Euler equations at dt=5e-4 (0.0031% at half that, sign-reversed);
      elliptic closed form and the machine-precision ODE agree to **7 digits** (8.759483); |L| drift
      **9.3e-03** and E drift **1.9e-02** over four flips (float32, not truncation — halving dt does
      not reduce it); minor/major-axis controls tilt **1.04°/0.87°** and do not flip.
- [x] **E2 `oscillating-sphere`** — unsteady Stokes drag vs Stokes (1851), complex. Headline
      **0.23%** at δ/R = 1 in the largest box (C = +2.00245 −1.21741i against +2.00000 −1.22222i);
      the δ/R sweep at L/R = 10 runs 0.25 / 0.29 / 0.43 / 0.95 / 2.48% over δ/R ∈ [0.5, 2.5], the
      last point being where δ reaches L/4 and the screening stops. Box ladder 2.48 → 0.43 → 0.23%.
      Steady calibration vs Hasimoto–Sangani–Acrivos: −1.50 / −0.47 / **−0.15%** at
      c = 0.0141 / 0.0042 / 0.0018, with the superficial-vs-interstitial convention settled ON THE
      DATA (fitted B = 0.90 vs the exact 1; interstitial gives 1.34). Three plan premises corrected
      — OPEN FOR REVIEW 2–4 — plus one bookkeeping error larger than any of them: the backward-Euler
      wall BC belongs at t^{n+1}, and imposing it at t^n rotates the fitted phase by ωΔt.
- [x] **E4a `pall-ring-packing`** — a certified-difference Pall ring, poured and measured.
      Certificate: **0.00%** of exterior probes violate the exactness bound (min slack +1.9e-12)
      against **24.68%** for the same solid built from the sign-exact leaf. ε = **0.797** ± 0.0007,
      f_env = 0.585, coordination 4.04, 0 rattlers, orientation |cos θ| = 0.469 ± 0.042. The claim
      is a **band and a mechanism**, not a percentage: holding the one measured f_env fixed and
      varying only the wall thickness walks ε from 0.741 (t/D = 0.16, the ceramic band) to 0.957.
- [x] **E5 `stirred-column`** (Phase 2, needs R1) — a pitched-blade impeller whose geometry actually
      sweeps. Lacey index **0.061 → 0.918** in five revolutions over 40 fixed bins × 553 grains;
      median peak grain speed **1.01×** the blade-tip speed (worst single sample 1.40×), **0** grains
      outside the column, two 1-thread runs bitwise identical. Literature comparison stated as
      qualitative — the meridional recirculation pattern of Remy et al. (2009), not their numbers.
- [~] **E7 `nonsphere-drag`** — equal-volume drag ratios validated against the exact Oberbeck
      spheroid solution before being used to predict cube/superquadric values.

### Suite fixes the examples produced
- **dem `53fab35`** (+ `5c53d41`, `326deb2`) — two out-of-bounds writes found by the pall-ring
  pour: the raw narrow-phase contact count used as a loop bound over `maxContacts`-sized views, and
  **twelve** capacity-sized per-body arrays never resized when the SoA grew. Measured effect beyond
  not crashing: mean coordination 3.38 → 4.04 and peak contact overlap 63% → 32% of the wall.
- **dem `6d27ba4`** — `step()`'s docstring claimed `dt=0` uses the configured time step; it does
  not, it runs a dynamics-free relaxation step. And the default **body-body** friction is zero,
  which silently lets a deep bed leak through an analytic wall (found building E5).
- **coupling `3b24934`** — `ResolvedCfdDem` can hand dem the reaction torque, **off by default**:
  the force's exactness rests on `-grad(pi)` telescoping over an owner region and that argument does
  not survive taking the first moment (|T|/(|F|R) = 3.2e-07 on a sphere whose true torque is exactly
  zero, against the traction integral's 5.0e-14).


Working through a batch of single-phase-flow benchmark examples for the gallery.
Each example is **self-contained** (creates its own SDF, sets all parameters
inline — no `channels.py`-style imports), executed against the local CPU build
(`PECLET_LOCAL_BUILD=…/flow/build_mpi`), frozen, committed, and pushed.

Legend: [x] done+pushed · [~] in progress · [ ] todo · [!] blocked/documented

## Tasks

- [x] Diagnose poiseuille "error" → metric artifact, not a solver bug (ISSUES.md)
- [x] Remove non-peclet `channel-mms`; drop helper-module imports; self-contained
- [x] Rewrite `poiseuille-ibm`: self-contained, **pointwise** error, both meshes — PUSHED
- [x] flow: rename `verify_poiseuille_sdflow.py`→`verify_poiseuille_flow.py`, pointwise — PUSHED (flow 6f0a312)
- [x] `pipe-poiseuille`: curved wall → genuine O(h²) convergence (order ~1.86) — PUSHED
- [x] `taylor-green`: exact NS, projection div-free ~1e-15, viscous decay — PUSHED
- [x] `lid-driven-cavity`: vs Ghia (rms 0.013 at 64²) — PUSHED
- [x] `zick-homsy`: SC convergence (+1.74%→+0.08%) + parametric K(φ) + BCC/FCC — PUSHED
- [x] `random-packed-bed`: dem LS packing (φ=0.66, Z=5.1, 0 rattlers) → ε,Z,g(r) →
      permeability (flat across N, ~1.5× Carman–Kozeny, 9% over realizations) — PUSHED
- [!] `backward-facing-step`: complete draft, COMPUTE-BOUND (>5min/Re, no steady on
      CPU). Moved to drafts/ (outside render path). Render on GPU to finish.
- [!] `cylinder-vortex-street`: DROPPED after exhaustive testing (see ISSUES for the
      full map). Two independent blockers: (1) inflow/outflow + immersed solid NaNs
      (real peclet.flow bug, localized to setSolid openness composition); (2) a Re~100
      wake needs D≳30 cells → large 2-D domain → ~20-40min/run = GPU-territory. The
      PERIODIC body-force path is stable (ran to Re~134, no NaN) and is the recommended
      route to build it on a GPU. Not shippable on CPU tonight without over-claiming.
- [ ] (stretch) other classics: Couette, Womersley, Kármán, Stokes problems — not done

## FINAL STATE (overnight session)
**6 examples live** at https://computational-chemical-engineering.github.io/peclet-examples/ :
poiseuille-ibm, pipe-poiseuille, taylor-green, lid-driven-cavity, zick-homsy,
random-packed-bed. Plus the flow verify-script fix (pushed to suite). CI green,
site current. The two unshipped examples are documented + preserved (BFS in drafts/,
cylinder deferred pending a peclet.flow inflow/outflow fix).

## Findings logged to ISSUES.md this session
1. Poiseuille metric artifact (resolved → reframed as exactness demo).
2. Immersed cut-cell pressure (cutcell_pressure=True) + inflow/outflow → NaN;
   workaround cutcell_pressure=False + all-fluid pressure. Real peclet.flow issue.
3. Random-packing permeability slow to converge on CPU (tight throats) — physical.
4. verify_poiseuille metric was lenient (fixed in flow, pointwise now).

## Findings / bugs (see ISSUES.md for full)
- Poiseuille metric artifact (resolved — reframed as exactness demo)
- Inflow/outflow NaN at under-resolved/odd config — BFS+channel scripts work at
  proper resolution, so likely config not a solver bug; will confirm per-example.

## Notes for future me
- Local CPU build: `PECLET_LOCAL_BUILD=/home/frankp/Codes/suite/flow/build_mpi`,
  `OMP_NUM_THREADS=4 OMP_PROC_BIND=spread OMP_PLACES=threads`.
- Quarto binary: scratchpad `quarto-1.5.57/bin/quarto`. Render: `quarto render`.
- Regenerate a Colab notebook after editing a qmd: `quarto convert examples/<slug>/index.qmd`.
- Keep grids modest — CPU-only overnight. Commit+push each example when green.

- [!] random-packed-bed packing is INVALID: dem periodic-collision bug (cross-boundary
      contacts missed) → real overlaps → inflated φ/Z and bad g(r). CONFIRMED (2-particle
      repro in ISSUES). Walled packing is clean (workaround). Needs dem fix or rework.

- [x] random-packed-bed FIXED (dem 0.2.1 periodic-collision fix): regenerated clean —
      φ=0.629, Z=6.63, 0 rattlers, g(r)=0 for r<d, k ~6% above Carman-Kozeny. Uses the
      effective radius (scale*growth_factor) + annealed pack.py protocol. PUSHED.

## Inflow/outflow examples (peclet-flow 0.2.1 released)
- [x] RELEASE: peclet-flow 0.2.1 (inflow/outflow fix + set_backflow_stabilization +
      set_deferred_correction) + peclet 0.2.2 metapackage. Both on PyPI. tag v0.2.1
      (flow) / v0.2.2 (umbrella). pip install peclet now has the fix.
- [x] developing-channel: uniform inlet -> Poiseuille (u_max/Um=1.493, L_e~0.04ReH). LIVE.
- [~] cylinder-vortex-street (Schafer-Turek 2D-2, Re=100): SHEDS at D=10 with
      deferred-correction advection, St=0.267 (bench ~0.30), dP~2.5. Rendering (~70min).
      C_D/C_L need a force-on-solid binding flow lacks. nav+gallery+ISSUES prepped.

## Rayleigh-Bénard example (2026-07-09)

- [~] `rayleigh-benard`: 3-D RB convection on GPU (scalar transport + Boussinesq
      closure, both already in peclet-flow — no solver changes needed). Two
      quantitative benchmarks: (1) onset — growth/decay rates bracket
      Ra_c = 1707.76 (Chandrasekhar) to ~0.4%; (2) cubic cell at Ra=1e6/3e6,
      Pr=0.7 vs Xu, Shi & Xi (2019) LBM-DNS (Nu=8.34/11.47) — 96³ prototype gave
      Nu = 8.37-8.42 ± 0.04. PyVista plume still + mp4 movie. Production render
      (128³ + 144³, ~4.5 h RTX 5080) in flight; commit after freeze.
- Solver settings that matter (in-page): explicit TVD advection,
  `set_velocity_solver_params(12)` (default 200 sweeps is 6x the step cost here),
  `set_pressure_pcg(True, 60, 1e-2)` + warmstart (36 ms/step at 128³);
  onset uses capped `pcg(12, 1e-6)` — see the two new flow entries in ISSUES.md
  (PCG relative stop never fires on near-quiescent fields; standalone V-cycle
  driver ~30x slow + n_pois not honoured).
