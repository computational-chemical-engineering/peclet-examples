# peclet 1.1.0 scaling campaign — state

*Rewritten in place at every milestone. A position, not a diary.*

## Objective

Replace the 1.0.0 scaling record (page + unpublished Zenodo deposit) with one measuring the
**1.1.0** implementation only. **No historic data from previous implementations appears in the
page or the dataset** (user directive, 2026-09-16) — this is a record of one version, not a
comparison.

## What "1.1.0" is

**Released 2026-09-16.** The record measures the tag, not a pre-release commit.

| repo | at `v1.1.0` |
|---|---|
| umbrella | `24b0417` (tag `v1.1.0`) |
| core | `094d2cb` (tag `v1.0.2`) |
| flow | `b90e6d5` (tag `v1.1.0`) |
| morton | `6e8abef` (unchanged) |

The first trees were built before the tag existed, at umbrella `5b527ec`. The delta to the
release is **version strings only**: flow gains one release commit (versions + the core repin),
core gains the clang-format commit (comment re-wrapping, checked) plus its own release commit,
morton is identical. So those builds were numerically the release — but they reported
`flow.__version__ = 1.0.1`, and a record titled 1.1.0 whose raw data says 1.0.1 does not ship.
**Both trees are therefore rebuilt at the tag**, under the name `v1.1.0-tag`, and every published
run comes from those.

## Why the numbers must be re-measured rather than carried over

The default momentum solver changed after 1.0.0 (`8acab7c`, superseded by `3e37758`): chosen now by
the implicit-diffusion operator's condition number, kappa = 1 + 12D, velocity multigrid at
kappa >= 13. Every run of the 1.0.0 study is at D = 6 (kappa = 73), so 1.1.0 runs this case with the
V-cycle where 1.0.0 ran red-black at its 200-sweep cap. Measured on the 1.0.0 campaign, that is
2.19x on one H100 and 1.81x on four — and it moves the PHASE MIX toward the projection, which is the
phase that scales worst, so the weak-scaling efficiency must be re-measured and is expected to
differ from 1.0.0's 79 %.

The physics is unchanged: the only other compute-path commits (`e144a00`, `d05eb15`) are gated on
NON-periodic domain faces and this study is triply periodic.

## Where we are now

**MEASUREMENT COMPLETE. Page and deposit built. Not yet published.**

39 runs at the v1.1.0 tag: 35 primary + 4 targeted repeats. All report `flow_version 1.1.0` and
`velocity_solver multigrid`. No failures.

| | 1.1.0 |
|---|---|
| Weak, 32 H100 @ 1.81 Gcells | 30.8 → 19.8 Mcell/s per GPU, **64 % efficiency**, iterations flat 29.7 → 29.8 |
| Strong, genoa 24 → 1536 cores | 36.3 s → **0.89 s**, 40.9×, **64 % of ideal** |
| Strong, 1 → 32 H100 | 1.8 s → 0.54 s, 3.4× (11 % of ideal) |
| Gate ⟨u⟩ | **8e−11** worst over 27 runs, 1 → 1536 ranks, both backends |
| TGV control | 4e−16 over 7 runs; weak 73 % |
| Permeability | k/R² = 0.017122, 3 rungs, spread 5e−13 |
| Depth control | 4 levels costs **81×** (179 435 vs 2 202 ms) at 8 GPUs, iterations unchanged |

**Why weak efficiency is 64 %** — from this record's own phase timers: momentum is 828 ms at the
base and grows 38 %; the projection is 1006 → 1705 ms, +70 %. The cheaper momentum solve leaves the
step dominated by the phase that scales worst.

**The 16-GPU strong rung is anomalous, reproducible and undiagnosed.** 1349 ms against 574 at 8 and
539 at 32; 4 allocations agree to 1.02×. Momentum sweeps (29) and pressure iterations (29.7) are
IDENTICAL at all three rungs, so it is not convergence — the same work runs ~2.3× slower.
Decomposition shape is ruled out on monotonicity (S/V 0.0312 / 0.0417 / 0.0521, worst-shaped rung
fastest).

## Built and waiting

- page `index.qmd` (rendered, no placeholders), figures, `gates.md`, `summary.md`, `headline.json`
- deposit `zenodo/build/`: tarball + HTML + PDF + both build censuses + `MANIFEST.sha256`
- `benchmarks/index.qmd` card now points at this record

## Next action — needs the user

1. **Delete `benchmarks/release-1.0.0-scaling/`.** The replacement is done everywhere else, but the
   removal was blocked as an irreversible local action, so the superseded directory is still in the
   tree. Its history is in git either way.
2. **Merge `bench/release-1.1.0-scaling` into main and deploy** (the site publishes from main).
3. **Zenodo:** `ZENODO_TOKEN=... ./zenodo/make_deposit.sh --upload` creates a DRAFT; publishing is a
   deliberate click and mints the DOI.
4. **MORPHO:** the drafted edit now needs 1.1.0's numbers — **1.8 Gcells at 64 % with cut-cell IBM**
   (73 % for the geometry-free control), not the 79 %/88 % drafted against the previous record.

## Budget (checked 2026-09-16)

- **GPU `2307092_26/L2/257`: 40,731 SBU remaining, EXPIRES 2026-10-31.** The 1.0.0 campaign cost
  ~20-25 k. 1.1.0 steps are ~2x faster, so the same ladders should cost less — but this is the only
  GPU budget and it does not survive a second full re-run. Right-size every rung; billing is per
  *allocated* GPU, so the 1- and 2-GPU rungs must override `--gpus-per-node`.
- CPU `NWO-2024.005/L1`: 3,250,947 SBU (genoa/rome), expires 2027-04-07. Not a constraint.

## Next action

1. Recon: harness surface + the flow API diff (does the 1.0.0 driver still run?).
2. Provision two build trees on Snellius, one per backend, from the pinned commits.
3. Pilot rungs, go/no-go.
4. Ladders; then analysis, page, deposit.

## Anchors

- worktree `~/Codes/peclet-examples-scaling-1.1.0`, branch `bench/release-1.1.0-scaling`
- remote campaign dir (planned) `/projects/0/prjs1022/peclet/bench-1.1.0`
- remote build trees (planned) `/projects/0/prjs1022/peclet/suite-v1.1.0-bench-{cpu,h100}`
- the record being replaced: `benchmarks/release-1.0.0-scaling/` (git history retains it)
