# peclet 1.1.0 scaling record — decision log (append only)

What was chosen, what was rejected, and why. The evidence lives in `summary.md`, `gates.md`,
`headline.json` and the raw `results/**/*.json`.

2026-09-16  SCOPE: this record measures ONE implementation.
  USER DIRECTIVE. The page and the dataset report peclet.flow 1.1.0 and contain no data from any
  earlier version — not as a comparison, not as a baseline, not in the figures. Rejected: carrying
  the predecessor's ladders for contrast, which would have made the record a version comparison
  rather than a statement of what this release does.
  Consequences, all executed: the companion pinned-solver campaign and its overlay figure were
  removed from `analyze.py`; every amendment callout was stripped from the page source; figure
  titles derive the version from the data instead of a literal.

2026-09-16  MEASURE THE RELEASE TAG, not the commit that was about to become it.
  The first trees were built at umbrella 5b527ec, before v1.1.0 was tagged. The delta to the tag was
  checked rather than assumed: flow gained one release commit (version strings + the core repin),
  core gained a clang-format commit (comment re-wrapping) plus its own release commit, morton was
  identical — so those builds were NUMERICALLY the release. They were still discarded, because they
  reported `flow.__version__ = 1.0.1` and a record titled 1.1.0 whose raw data says 1.0.1 does not
  ship. Both trees were rebuilt at the tag and the two pilot runs taken on the earlier build were
  deleted rather than kept.
  Evidence: `census-h100.txt` / `census-cpu.txt` (umbrella 24b0417, tag v1.1.0).

2026-09-16  `install_bench.sh` accepts a tag, a branch OR a commit SHA.
  It cloned `--branch <tag>`, which cannot express "the commit that will become the release". Now it
  clones, then `checkout --detach`, with a third argument decorating the path. The census records
  the RESOLVED sha, which is what the record cites.

2026-09-17  A RUN REFUSES TO START against a build it was not asked for.
  The trees are named `v1.1.0-tag` while the run scripts default `TAG_VERSION=v1.1.0`, so one
  forgotten export would have silently measured the superseded build — the failure mode this suite
  has lost campaigns to. `EXPECT_FLOW_VERSION` is compared against `peclet.flow.__version__` at the
  head of every run and the job dies if they differ. Rejected: remembering to pass it.

2026-09-17  THE LADDERS WERE RELEASED WITHOUT WAITING FOR THE 4-GPU PILOT.
  The pilot had been PENDING 5 h on a partition with 51 nodes allocated and 12 reserved. Serialising
  34 jobs behind it would have cost hours for information the per-run version guard already
  enforces; a broken multi-GPU halo fails fast rather than consuming the 45-minute cap, and runs on
  the same `core` the previous campaign exercised to 32 GPUs. The pilot stayed queued as a canary.
  Rejected: waiting, at a cost measured in hours per rung.

2026-09-18  THE MOMENTUM SOLVER IS RECORDED BY NAME, and the sweep count with it.
  1.1.0 returns `diagnostics.velocity_solver()`; the record stores it rather than inferring the
  solver from a boolean. `momentum_sweeps` — which the solver already returns — was added to the
  per-step whitelist after it turned out to be the key that decides whether a slow rung is doing
  more work or the same work more slowly. Both are read through a guard so a missing diagnostic
  cannot destroy a completed run's timings.

2026-09-18  THE GATE'S PRIMARY CONFIGURATION IS DERIVED FROM THE DATA.
  The grouping hard-coded "primary = velocity multigrid OFF", which was the predecessor's default.
  Under 1.1.0 every run has it ON, so the primary group came out empty and `render_page.py` refused
  to build the page. Fixed by taking the majority configuration as primary. The grouping itself is
  KEPT even though this record has only one configuration: it exists to CATCH a split, not to
  average over one.

2026-09-18  ONE STATED DEPARTURE FROM SHIPPED DEFAULTS: multigrid depth.
  The pressure multigrid is asked for as much depth as the grid admits rather than the default four
  levels, because depth is a property of the grid. The cost of the default is measured rather than
  argued: the same 8-GPU weak rung at four levels takes 179 435 ms per step against 2 202 ms at full
  depth — 81× — at an unchanged iteration count. That run is in the tables and excluded from every
  ladder. Everything else is shipped default.

2026-09-18  THE 16-GPU STRONG RUNG IS REPORTED, REPRODUCIBLE AND UNDIAGNOSED.
  It takes 1349 ms against 574 at 8 GPUs and 539 at 32 — 2.3× slower than both neighbours. Three
  further allocations were run specifically to test it; they agree to 1.02×, so it is not placement.
  Momentum sweeps (29) and pressure iterations (29.7) are identical at all three rungs, so it is not
  convergence: the same work executes ~2.3× slower. The decomposition-shape explanation is
  REJECTED on this record's own data — surface-to-volume is monotone (0.0312 / 0.0417 / 0.0521) and
  the worst-shaped rung is the fastest. Rejected: omitting it, or quoting the ladder without it.
  Evidence: `hierarchy_predict.txt`, the `_sweeps` runs, `summary.md`.
