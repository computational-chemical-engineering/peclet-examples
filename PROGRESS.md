# Overnight build progress

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
