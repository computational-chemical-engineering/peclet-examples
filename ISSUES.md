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

## Inflow/outflow channel diverges to NaN at low resolution
- **Status:** open
- **Package / area:** flow — inflow/outflow domain BC + semi-coarsening pressure MG
- **Found in:** scratch run while prototyping `poiseuille-ibm` (the developing
  inflow→outflow channel variant; we shipped the periodic body-force case instead)
- **Observed:** `U_mean=nan`, `max_open_divergence=-inf` after 3000 steps.
- **Expected:** a developed parabola, `u_max/U_mean → 1.5`, finite divergence —
  as `scripts/verify_channel_sdflow.py` produces at its defaults.
- **Repro:** `flow.Solver(L=160, H=24, nz=4)`, `set_mu(U*H/Re)` with `U=1, Re=100`,
  `dt=0.5`, inflow BC face 0 (type 2, U), outflow face 1 (type 3), no-slip ±y,
  `set_pressure_multigrid(True, levels=8)`, `set_pressure_solver_params(80)`,
  `set_pressure_geometry(all-fluid)`; OpenMP backend, 4 threads.
- **Notes:** The canonical script uses `H=32, L=224` and passes. Suspect the
  combination of a small/odd `H=24` with `levels=8` semi-coarsening (which caps
  levels by even-axis divisibility) and/or too few pressure iterations for the
  entrance-length transient. Need to bisect: does it NaN at `levels` auto-capped
  low, or only deep? Is `H` divisibility the trigger? Determine whether this is a
  robustness bug (should degrade gracefully / warn) or expected for an
  under-resolved config that the API should reject.

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
