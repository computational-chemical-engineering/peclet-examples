# Drafts (not built into the site)

Examples that are written but **not yet shippable**, kept here (outside the Quarto
render path) so the work is preserved without breaking the site build. See
[../ISSUES.md](../ISSUES.md) for the blocking reasons.

- **backward-facing-step** — complete and physically set up, but the Gartling
  reattachment does not converge within a feasible CPU step budget (>5 min per
  Reynolds number, did not reach steady state). Compute-bound; render on a GPU build,
  or with a much longer step budget, then move it into `examples/`.

A companion **cylinder vortex street** was attempted and dropped: immersed solids +
inflow/outflow are currently broken in `peclet.flow` (see ISSUES.md — the geometry
setters clobber each other, `cutcell_pressure=True` NaNs, and `False` leaks no-slip),
and the case is ~19 min/run on CPU. It needs a solver fix first.
