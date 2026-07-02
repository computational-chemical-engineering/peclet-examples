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
