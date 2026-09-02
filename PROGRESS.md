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
- [x] **E7 `nonsphere-drag`** — equal-volume drag ratios, validated against the exact Oberbeck
      spheroid before predicting anything. Sphere calibration **−0.62%** vs Hasimoto–Sangani–Acrivos
      with a fixed point independent of dt to 3.7e-04; prolate AR=2 **−1.57%** axial / **+2.90%**
      broadside vs exact (box shift −1.8%/+2.2% in the same directions — box-limited, not
      model-limited); **cube orientation-independent to 0.14%**, as cubic symmetry demands, at
      1.08846 against the tabulated χ = 1.08 ± 0.01; rounded cubes 1.08363 / 1.04143 vs Štrakl et
      al. Three results beyond the gate: Leith's 9% orientation spread for a cube is a correlation
      artefact; Haider–Levenspiel has NO Stokes limit (B(ψ) > 0 ⇒ C_D → 24/Re for every ψ); and a
      **bound-only** geometry leaf gives drag identical to a distance-exact one to six digits,
      because the cut-cell geometry uses the zero level set and the crossings, not the distance.

### Follow-up (requested after the batch): moving geometry
- [x] **`moving-sphere-drag`** — the sphere PHYSICALLY translates through the grid. Spurious force
      oscillation measured with the literature's own metric (Seo & Mittal Eq. 12 second difference)
      plus a 5-harmonic residual: **3.07e-02 against a static-geometry floor of 6.98e-04**, i.e. 44×,
      with a **resolution-independent +2.6…+2.9% drag bias** on top (+2.91/+2.61/+2.71% at
      R/h = 6.4/9.6/12.8 — refinement was never going to fix it). Refining Δt makes it **worse**
      (2.80e-02 → 4.13e-02), the literature's signature that the source is spatial.
      **Fresh-cell seeding** (new `set_fresh_cell_seed`, now the flow default) takes the oscillation
      to **9.55e-04**, within 1.4× of the non-moving floor, and the bias to −0.04%. Beyond Stokes,
      the peak drag converges onto Blackburn (2002) Table II: **+10.27 → +2.10 → −0.42%** at
      δ/h = 4.05/5.06/6.32, box independent to **0.1%** between L/D = 7.5 and 10, and a
      half-amplitude bracket lands on the same δ/h curve.

- [x] **`rotating-sphere-torque`** (requested) — a **negative result, fully diagnosed**. The Stokes
      torque 8πμa³Ω is exact and a sphere is invariant under its own rotation, so the geometry never
      moves: the cleanest possible torque test. The discrete-reaction torque is **−31.0%**, flat over
      a factor of 8 in box volume, 3.4 in solid fraction, 2 in R/h, and from 600 to 4000 steps. Net
      force on the same runs: **1e-13**. Cause, exact: the viscous operator is the Laplacian
      ∇·(μ∇u), not ∇·[μ(∇u+∇uᵀ)]; for the rotlet (∇uᵀ)·n is exactly **half** of (∇u)·n pointwise on
      the surface, so the transpose carries exactly **one third** of the torque — predicted −33.33%,
      measured −31.0%. It hides because that term integrates to **zero in the force** but not under
      the r× weighting. Same plateau Maitri et al. (2018) measured (34.34/33.04/33.24/33.32%) on the
      Deen et al. (2012) IBM. A second, independent defect: the **traction** torque drifts linearly
      with step count on a steady field (−26% → +83%) because the cut-cell operator decouples
      solid-centred pressure cells — std(P) is 7.3e-07 and constant in the fluid, 2.5e-04 → 1.6e-03
      and linear in the solid. ~~Consequence: E8 blocked.~~ **SOLVED 2026-08-31 (flow `16e91ec`):**
      the missing traction on a rigid rotating no-slip wall is **μ(n×Ω) pointwise** — derivable in
      three lines from the rigid-body tangential derivatives plus continuity, rotlet-verified to
      3e-11 — with force integral **zero** (why no force gate ever saw it) and torque integral
      exactly **one third**. The fix integrates μ r×(n dA×Ω) over the cut cells with the exact
      apertures: closed form, no reconstruction. Gate: −31% → **+3.47/+2.42/+2.19%** converging;
      spin-decay through `ResolvedCfdDem` `apply_torque=True` at **1.0389×** the same-box calibrated
      drag. The page is rewritten as *negative result → diagnosis → fix → gate*. **E8 UNBLOCKED.**

### Phase 2/3 remainder — executed 2026-08-30/31
- [x] **E8 `jeffery-orbit`** (`954e711`) — prolate spheroid r=2 tumbling in wall-driven shear,
      torque-coupled through `set_external_torques` with the physical Jeffery inertia. Half-period
      via φ-crossings separated by π (transient-immune): **−3.42% (96³) / −5.01% (128³)** against
      T = (2π/γ̇)(r + 1/r). En route it exposed the **−44% period** that became the v4 owner-flux
      attribution fix (flow `1d95260`), and the **lattice-plane trap** (plate faces on a grid plane
      → zero cut cells → moving wall silently inert; PLATE half-thickness must be off-lattice, 8.3).
      r=4 at b=3.5h is a documented **failure** (needs b≳5h ⇒ ≥160³) and is out of CASES.
- [x] **E4b `pall-ring-flow`** (`797effd`) — Stokes flow through E4a's frozen 41-ring pour.
      Certified-vs-shell `set_solid`: **0.21 s vs 0.88 s (4.1×)**. Ergun with the **Sauter**
      diameter Dp = 6V/S (V=0.268, S=6.561 per unit-radius ring — envelope Dp is 2.9× off):
      measured/Ergun = **0.96 / 0.96 / 0.96 / 0.95** over the ladder. Per-ring reaction-drag
      density resolved in the bulk window y ∈ [1.0, 4.47].
- [x] **E9 `dumbbell-drag`** (`0e682dc`) — touching equal-sphere dumbbell vs the exact bispherical
      solutions, drag ratio K to the equal-volume sphere in the SAME box so the box cancels:
      edge-on **1.02485 (+0.07%) → 1.02532 (+0.12%)** vs 2·0.64514/2^{1/3} (Stimson–Jeffery);
      broadside **1.19998 (+4.32%) → 1.18250 (+2.80%)** toward 2·0.72462/2^{1/3} (Jeffrey–Onishi).
      (Chosen over sedimentation: steady drag is the claim the exact solutions actually gate.)
- [x] **E3a `ten-cate-sphere`** (`e1008a1`) — SHIPPED as a **diagnosed negative result** (the
      rotating-sphere-torque precedent). Passes: Galileo similarity 1%, towed-vs-free-fall
      consistency 2%, unconfined periodic control 1.03 of the screened expectation. Fails,
      diagnosed: E1 peak u/u∞ = 0.781/0.777/0.749 (d/h 8/12/16) vs measured 0.947 —
      resolution-flat at the **creeping** confined value, invariant to dt/2, sweeps ×3.3,
      SOU→Koren, advection off; E3/E4 coupled falls **exceed u∞** (2.16/1.87); Newton audit on a
      towed Re-32 sphere leaks +0.32 W. One suspect: the **advective cut-wall flux** (suite §7
      item 8; addendum with these numbers pushed, suite `4f754b1`). En route: first render hung 8 h
      (asymptotic-only loop exit — now kmax + post-peak stop, armed past 0.6 u* only), MG-hostile
      odd grid cost 10× (549→56 s per fall), virtual-mass stabilizer (ma = 2ρfVp, lagged
      compensation) for the ρp/ρf = 1.15 explicit-coupling ring-up.
### The A0 solver rung the benchmark bought (2026-08-31)
- [x] **Advective cut-wall flux, rung A0** (flow `fb1a1a7` + `469ab7f`, suite `918cf9f`) — the
      `ten-cate-sphere` page's diagnosis paid off as a real solver fix: the momentum-advection
      kernels read `maskVelocity`'s solid ZEROS, and zero is the wall velocity only for a static
      wall. Feeding them the rigid-body `u_wall` closed the towed-E4 Newton leak
      **+0.322 → −0.033 W** (below that probe's own advection-off floor, −0.070) and cut
      `moving-sphere-drag`'s Blackburn finite-Re peak-Cd error from **10.3% to 2.2%** worst case.
      Static scenes **byte-identical** (60/60 MPI ctests np=1,2,4; regression +0.00% every metric).
      **ten-cate did NOT recover** (E1 0.803/0.797/0.766 vs 0.947; E3/E4 still above u∞) ⇒ the
      confined finite-Re deficit is a DIFFERENT defect and rung A1 is **not** indicated. Both
      affected pages rewritten + re-rendered (the moving-sphere δ/h "convergence" story was largely
      this error decaying). Three live threads recorded in the plan doc.

- [ ] **E3b `drafting-kissing-tumbling`** — **DEFERRED with cause**: DKT is finite-Re coupled
      two-body motion, the exact regime E3a just measured as quantitatively broken (creeping-valued
      confinement + momentum leak). Building it before the §7-item-8 solver fix would ship a
      known-bad benchmark. It becomes the natural second regression page after the fix.

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
- **flow `1d95260` (v4, owner-flux attribution)** — with several bodies, the per-body reaction
  force/torque mis-attributed the π-flux across owner-region boundaries (fluid–fluid staggered
  faces whose two cells have different owners). Fix removes it pairwise (`hydro_reaction_owner_flux`,
  each side's own min-imaged lever). Found by E8's −44% Jeffery period; sphere-in-tank drag went
  λ = 0.62 → correct.


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

## Two-phase VoF examples (2026-09-02)

- [x] `parasitic-currents` (E2 of the VoF gallery work order): the stationary droplet.
      Balanced-force CSF vs the cell-centred/interpolated ablation with an EXACT curvature —
      max|u| 1.88e-17 vs 5.76e-2, a factor 3.07e+15 on one operator pairing; with the
      computed curvature Ca = 2.543e-4 / 5.898e-5 / 2.649e-5 / 1.388e-5 at D/dx = 8/16/24/32,
      fitted order 2.09; the wisp-guard ablation (`set_vof_interface_eps(0)`) at 64^3 —
      max|kappa| 0.126 -> 2.87e+11 and the currents stop decaying; the curvature branch census
      (PLIC fallback 71% at D/dx = 8 down to 22% at 32, branch 6 empty everywhere).
      All four sweep rungs converged their pressure solve (12-13/500).
- [x] `rising-bubble` (E4): Hysing et al. (2009) cases 1 and 2 on 64x128x4, adaptive
      dt = 0.4 min(WY CFL, capillary). Case 1 max V_c 0.2497 (ref 0.2417, +3.3%),
      y_c(3) 1.0808 (ref 1.0810, -0.02%), 2032 steps, capillary binds 204/204.
      Case 2 0.2574 (+2.9%) and 1.1082 (-2.6%), 1123 steps, WY CFL binds 108/113,
      pressure 116/600 and max|div| 1.85e-3 (the ratio-1000 conditioning; not capped).
      Momentum-consistency A/B on case 1: OFF gives 0.2827 (+17.0%) and 1.2086 (+11.8%),
      i.e. consistency is worth a factor ~5 in the centroid error AT RATIO 10.
      Bubble volume V(3)/V(0) = 1.0000000000.
- Both pages end with a "Collocated cross-check" stub: the two-phase collocated path is
  rung V8 of the VoF campaign and is not yet available.
- Two new ISSUES entries: no free-slip domain BC (periodic stands in; exact for Hysing case 1,
  an approximation for case 2), and no VoF interface-area binding (so benchmark circularity
  cannot be reported).
- Solver build used for the frozen outputs: `suite/flow-vof/build_cuda` (CUDA, flow main).
- [x] `capillary-oscillations` (E3): surface tension as a *restoring force*, against exact
      viscous normal modes (both reference functions copied into the page; the drop's needs
      mpmath). Part A, standing capillary wave (quasi-2D, walls ±z, a0 = λ/100, 2.5 periods):
      ω = 0.06018 / 0.02131 / 0.05929 at 32 & 64 cells/λ with ν = 0.005 and 32 with ν = 0.02,
      i.e. **−0.02 / −0.19 / +0.54 %** against the exact two-fluid root
      `s² + ω₀²(1 − k/√(k²+s/ν)) = 0` (with the tanh kH wall factor) — while the SAME runs read
      −2.19 / −2.04 / −3.63 % against the inviscid ω₀² = σk³/2ρ, which is exactly the
      "−2…−4 % deviation" WO-P recorded and could not explain. The decay: exact rate is
      1.7–3.9× the free-surface 2νk² (an O(√ν) interfacial boundary-layer rate), and the fitted
      decay lands within 24 % of it. Estimator: a damped-sinusoid least-squares fit
      (A e^{−γt} cos(ωt+φ) + B, first quarter period skipped) with the zero-crossing and
      two-extremum estimators printed beside it.
      Part B, mode-2 drop (48³, R = 8, φ = 1.9 %, ε = 0.05, μ = 0.0025 / 0.02): ω = 0.09142 /
      0.09072 = **−5.58 / −6.30 %** vs Lamb; the exact viscous mode (Miller & Scriven) accounts
      for −1.78 / −5.03 %, leaving −3.87 / −1.34 %. The μ = 0.02 residual is an over-subtraction
      (the run's damping is 17 % below the exact rate because √(ν/ω₀) is 0.45 cells), so the
      honest number is the low-viscosity rung's **≈ 4 % inviscid, resolution-independent
      deficit** — published as an OPEN measured deviation with the list of what it is not
      (not the reference, measurement, confinement, resolution, amplitude, dt, or the curvature
      estimator — freezing κ exact makes it *worse*). Nothing was tuned.
      Health: pressure 10–12/500 on every run, max|div| ≤ 7.1e-13, drop volume drift −1.4e-14,
      curvature branch 6 (no estimate) empty, PLIC fallback 37 %.
      Two new ISSUES entries: the ~4 % mode-2 deficit, and the shipped `wave`/`lamb` study gates
      comparing against the inviscid/free-surface references (the exact ones now exist in
      `tests/study/vof_capillary_references.py` but the gates do not use them); plus a note on
      the existing free-slip-BC entry.
