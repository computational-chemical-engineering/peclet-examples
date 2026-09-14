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

Two findings the page reports rather than smooths: the reproducible 16-GPU strong-scaling
anomaly (projection phase, hypothesis flagged untested), and that the CPU ladder's apparent
122 % of ideal is a flattered baseline plus the automatic momentum-solver switch.

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

## Next action — needs the user

1. **Zenodo draft upload** — `ZENODO_TOKEN=... ./zenodo/make_deposit.sh --upload`. Not run: it
   uses the user's token. Publishing afterwards is a deliberate click; it mints the DOI.
2. **MORPHO** — once the DOI exists, swap `PecletBenchmarks` (`morpho-application-M1.tex:240-247`,
   a TODO the proposal already carries) and update the sentence's numbers: the record supports
   1.8 Gcells at 79 % with cut-cell IBM (88 % without), where the
   proposal currently says 1.7 Gcells at 86 % from the older channel-DNS page. Part A is closed:
   this is the user's call, not an edit to make unilaterally.
**The measurement is closed.** 41 runs, queue empty, all repeats folded in: three separate 8-node
allocations at 1.81 Gcells agree to 1.00x, and every repeat in the study sits between 1.00x and
1.06x. Nothing further is queued.

## Budget

- **GPU: 43,604 SBU ≈ 227 H100-hours, EXPIRES 2026-10-31.** Estimated campaign ~20–25 k SBU.
  Billing is per *allocated* GPU: the 1- and 2-GPU rungs must override `--gpus-per-node`.
- CPU: 3.5 M SBU on genoa; the ladder costs ~3.5 k. Not a constraint.

## Open decisions (with their defaults)

- Zenodo licence: CC-BY-4.0 for the data, the repo's licence for the scripts. *Default: proceed.*
- Whether the deposit's report is HTML or PDF. *Default: both, rendered from one source.*

## Anchors

- driver `scaling_bench.py`, bed `make_bed.py`, rungs `snellius/run_{gpu,cpu}.sh`,
  provisioning `snellius/install_bench.sh`
- remote campaign dir `/projects/0/prjs1022/peclet/bench-1.0.0`
- MORPHO ref [14] TODO: `~/Codes/proposal/ENW-M/morpho/morpho-application-M1.tex`
