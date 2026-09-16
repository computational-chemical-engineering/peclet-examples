# peclet 1.0.0 scaling deposit — campaign state

*Rewritten in place at every milestone. A position, not a diary; the history is in `DECISIONS.md`.*

## Objective

A citable **Zenodo Dataset** recording the parallel performance of **peclet.flow 1.0.0 + cut-cell
IBM**, and a companion gallery page. Cited from the MORPHO (NWO ENW-M) proposal, which currently
carries a gallery URL as ref [14] with a TODO to swap it for a DOI.

Peclet-only: **no FoxBerry, no external codes** (user decision, 2026-09-12).
The report states 1.0.0's performance; it does **not** narrate improvements or history.

## The study

One case family: **creeping flow through a periodic random sphere packing, cut-cell IBM, triply
periodic, body-force driven**. One unit cell = 1043 spheres at φ=0.45 in a cubic box of 21.333 R
(`bed_phi0.45_r18_s0.npz`, grown with the released peclet-dem 1.0.0), R = 18 cells at 384³.

| Ladder | Machine | Configuration | Rungs |
|---|---|---|---|
| **W** weak (headline) | gpu_h100 | 384³ cells/GPU, the unit cell tiled | 1→32 GPUs, 56.6 M → 1.81 Gcells |
| **S** strong (CPU) | genoa | fixed 384³ unit cell | 24 → 1536 cores |
| **T** strong (GPU) | gpu_h100 | fixed 384³ unit cell | 1 → 32 GPUs |
| **N** no-IBM control | both | Taylor–Green, same grids | subset of rungs |

Every run starts from rest and takes the same steps, so **⟨u⟩ after WARMUP+NSTEPS is one number
that every rung of every ladder must reproduce** — the free per-rung correctness gate. The
permeability march (phase B, `MARCH_TOL=1e-5`) runs only at a few rungs.

## Where we are now

**The measurement is complete: 40 runs, every gate passing, committed with its raw logs.**

| | |
|---|---|
| Weak, H100 | 14.07 → 11.2 Mcell/s per GPU, 1 → 32 GPUs = **79 % at 1.81 Gcells**; pressure iterations flat 29.7 → 29.8 |
| Weak, control | 88 % at 32 GPUs, 8.0 iterations flat |
| Strong, genoa | 71.1 s → **0.91 s**, 24 → 1536 cores (78.0×) |
| Strong, H100 | 4.0 s → **0.55 s**, 1 → 32 GPUs (7.3×) |
| Equivalence gate | ⟨u⟩ identical to **8e−11** over 28 runs, 1 → 768 ranks, both backends; control to 1e−16 |
| Permeability | k/R² = 0.017122, agreeing to 5e−13 across 5 rungs |
| One H100 ≈ | 348 genoa cores (conservative reading) |

Deposit packaged locally at `zenodo/build/`: tarball, self-contained HTML + PDF report,
build censuses, provenance, `MANIFEST.sha256` (~890 KB total).

Two findings the page reports rather than smooths: the reproducible 16-GPU strong-scaling anomaly
(projection phase; the decomposition-shape hypothesis was WITHDRAWN on 2026-09-15, contradicted by
this record's own monotone surface-to-volume ratios, and replaced by the list of what the anomaly is
not), and that the CPU ladder's apparent 122 % of ideal is a flattered baseline plus the automatic
momentum-solver switch — quantified on 2026-09-15 as 77 % pinned to red-black and 30 % pinned to the
multigrid over 24 -> 1536 cores.

## Published (2026-09-14)

The page is **live**: <https://computational-chemical-engineering.github.io/peclet-examples/benchmarks/release-1.0.0-scaling/>

It could not ride the normal pipeline: "Publish gallery to GitHub Pages" has been red since
2026-09-05 because another session's 1.0.0 API page ports are pushed while their regenerated
`_freeze/` outputs are not, so 47 pages re-execute in a CI that deliberately installs no peclet.
(Those commits reached origin because THIS session's `git push` carried them out of the shared
checkout — see DECISIONS.md.)

So this page was deployed surgically, and the branch `deploy/benchmark-1.0.0-page` records exactly
what went out: base `cde8b25` (the last green deploy, where every freeze matches its source, so the
render executes nothing) plus this page and its card — `git diff cde8b25..deploy/benchmark-1.0.0-page`
touches nothing else. Run 34819466850, build and deploy both green, verified live (page 200, all
three figures 200, headline numbers present in the served HTML). The `github-pages` environment
briefly allowed that branch; **the policy has been removed and is `main`-only again**.

The gallery campaign's own full deploy supersedes this entirely — at which point
`deploy/benchmark-1.0.0-page` can be deleted (`git push origin --delete deploy/benchmark-1.0.0-page`
and `git worktree remove`).

## Version scope — settled 2026-09-16

The push hold is lifted (main moved on, the gallery pipeline is green again) and everything local
is pushed: the two amendment commits, and a **version-scope note** (`b0a045b`).

The question that prompted it: **1.1.0 is about to be released — do these numbers still stand?**
They do, and the record now says exactly what they are a record *of*.

- **The physics is untouched.** The only compute-path commits since `flow v1.0.0` that could move
  this case are the SCALING_ISSUES #3/#8 open-face fix (`e144a00`, `d05eb15`), and it is gated on
  NON-periodic domain faces (`extendSdfDomainGhosts` skips `bc_[face] == 0`; the Dirichlet-aperture
  half only exists at an outflow). This study is triply periodic, so it is inert here.
  `k/R^2 = 0.017122` and the 8e-11 equivalence gate stand at 1.1.0.
- **The default momentum solver changed** (`8acab7c`, superseded hours later by `3e37758`): chosen
  now by the implicit-diffusion operator's condition number, kappa = 1 + 12 D isotropic, velocity
  multigrid at kappa >= 13. **Every run in this record is at D = 6.0** (41/41 runs carry
  `physics.diffusion_number = 6.0`; 37 ran with `velocity_multigrid_active = False`), so
  **kappa = 73** and 1.1.0 runs this entire study with the V-cycle.
- Consequence, both ways, now stated on the page and in the Zenodo description: absolute throughput
  at 1.1.0 is BETTER than every figure here by about the quoted headroom (2.19x at 1 GPU), while the
  EFFICIENCIES must not be carried across versions — this record's own pinned CPU ladder measures
  the V-cycle scaling WORSE than red-black (41 % of ideal against 79 %), so a faster default is
  expected to scale less steeply. 79 % is 1.0.0's number at 1.0.0's default.

**Decision: publish the 1.0.0 record as it stands rather than re-running at 1.1.0.** It is
version-pinned in its title, version field and provenance; `make_deposit.sh` cites the CONCEPT DOI,
so a 1.1.0 campaign later becomes version 2 behind the same reference the proposal carries. A
1.1.0 weak-ladder re-run is an optional version 2 (GPU budget expires 2026-10-31), not a blocker.

**One open accuracy question, cheap to settle** — see "Open questions" below.

## Open questions in the results themselves

A dedicated discussion of the performance results was requested on 2026-09-14; the agenda is in the
memory note `peclet-1-0-0-scaling-deposit.md`. Three of its six items were SETTLED by the 2026-09-15
amendment (the 122 %-of-ideal reading, the 16-GPU decomposition-shape hypothesis, and the
attribution of the projection's growth to global coupling — the record's own `pressure_allreduce`
timer puts the reduction at 0.6 % of the projection). What remains open:

- **The projection is where the weak ladder loses**: +68 % across 1 -> 32 GPUs against momentum's
  +12 %, at a FLAT iteration count (29.8). Not algorithmic — coarse-level latency plus a hierarchy
  that deepens 8 -> 10 levels along the ladder. That is where a next factor would come from.
- **The 16-GPU anomaly is unexplained**, now stated as what it is not.
- **Geometry's share of the weak loss**: 79 % (cut-cell) vs the control's 88 %, on a control that is
  NOT a clean IBM-cost comparison (it advects; the bed case creeps).
- **ACCURACY, opened 2026-09-16 — the one thing that could still touch a published number.** The
  momentum solve in this record ran at its 200-sweep cap and did not meet its tolerance: the rule
  committed in `flow 3e37758` measures red-black at D = 6 (this study's D) reaching residual 7e-08
  against a 1e-10 target. The timings are unaffected — they are what 1.0.0 did — but `k/R^2 =
  0.017122` is a *physical* number marched to steady state through that solve, and its quoted
  agreement of 5e-13 is cross-rung REPRODUCIBILITY, not accuracy. **Cheap decisive test: march the
  384^3 unit cell twice on ONE H100, red-black vs pinned velocity multigrid, and compare k.**
  Minutes of one GPU. If k agrees to the quoted digits the number is safe as published; if it moves,
  the permeability section needs a sentence. Worth running BEFORE the DOI is minted.

Everything needed to re-argue any of it is in `summary.md`, `gates.md`, `headline.json` and the
per-step arrays inside each `results/**/*.json`; `python analyze.py results` regenerates all of it.

## Next action — needs the user

1. **Zenodo draft upload** — `ZENODO_TOKEN=... ./zenodo/make_deposit.sh --upload`. Not run: it uses
   the user's token. The build in `zenodo/build/` is current as of 2026-09-16 and carries the scope
   note; deposit version `1.0.0+addendum.2026-09-16`. Publishing afterwards is a deliberate click;
   it mints the DOI.

2. **MORPHO edit — drafted 2026-09-16, apply after the DOI exists.** Part A is closed, so this is
   the user's call. Two edits, both already sanctioned by the TODO the proposal carries at
   `morpho-application-M1.tex:246-247`.

   **(a) `morpho-application-M1.tex:240-241`** — the numbers. Replace:

   > On the national supercomputer Snellius, weak scaling has been
   > demonstrated to 1.7 billion cells on 32 H100 GPUs at 86\% parallel efficiency, against a
   > published benchmark record~\cite{PecletBenchmarks}.

   with:

   > On the national supercomputer Snellius, weak scaling has been
   > demonstrated to 1.8 billion cells on 32 H100 GPUs at 79\% parallel efficiency with the
   > cut-cell immersed boundary active (88\% without it on the same grids), against a
   > published benchmark record~\cite{PecletBenchmarks}.

   The old 1.7 Gcells / 86 % came from the older channel-DNS page. 79 % is the defensible figure
   WITH the geometry, which is what MORPHO actually needs; quoting 88 % alone would be the
   geometry-free control. Then delete the two TODO comment lines at 246-247.

   **(b) `morpho.bib:308`** — retarget the reference from the gallery URL to the dataset DOI:

   ```bibtex
   @misc{PecletBenchmarks,
     author = {Peters, E. A. J. F.},
     title  = {Parallel performance of {peclet.flow} 1.0.0: strong and weak scaling of a
               cut-cell immersed-boundary incompressible flow solver on {Snellius}
               ({Genoa} {CPU}, {H100} {GPU})},
     year   = {2026},
     howpublished = {Dataset archived on Zenodo},
     note   = {\href{https://doi.org/10.5281/zenodo.NNNNNNN}{doi:10.5281/zenodo.NNNNNNN}
               (concept DOI, resolving to the latest version)}
   }
   ```

   Use the **concept** DOI Zenodo reports, not the version DOI, so a later 1.1.0 campaign updates
   the reference instead of stranding it. Rebuild the PDF and check the reference list renders.
