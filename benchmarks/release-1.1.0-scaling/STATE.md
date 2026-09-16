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

**Builds done, pilot green, ladders NOT yet submitted.**

Both trees built at the pinned ref and import correctly — `flow 1.0.1 space Cuda has_mpi True`
and `space OpenMP has_mpi True`. Census confirms umbrella `5b527ec`, core `e6a612d`,
flow `d05eb15`, morton `6e8abef` in both.

### Pilot (2 of 3 rungs; the 4-GPU rung is still queued)

| rung | ms/step | vmg active | pressure iters | gate ⟨u⟩ |
|---|---|---|---|---|
| 1 H100, CUDA | **1840.5** | True | 29.7 | 1.6388902085859007e-04 |
| 192 genoa cores, OpenMP | 8479.5 | True | 29.7 | 1.6388902085859007e-04 |

Two things this establishes before any real money is spent:

1. **The condition-number rule selects the V-cycle, as predicted.** 1840.5 ms is the number the
   previous campaign measured for the velocity multigrid *pinned by hand* (1840 ms) against its own
   default's 4025 ms. So 1.1.0's automatic rule now picks, by itself, what the old default could
   not.
2. **The equivalence gate agrees to the last digit across backends** — CUDA on one GPU and OpenMP
   on 192 ranks return the same ⟨u⟩. That is the property the whole record rests on.

### Two defects found and fixed in the pilot, which is what a pilot is for

- `velocity_solver()` is bound on **`diagnostics`**, not on the solver. The driver called
  `s.velocity_solver()` and got an AttributeError. The runs survived only because the diagnostic is
  read through a guard (`_opt`) that refuses to lose a completed run's timings to a renamed query.
  Fixed to `s.diagnostics.velocity_solver()` and re-synced; the queued 4-GPU rung picks it up.
- The build's `flow.__version__` is **1.0.1**, so every result JSON records `flow_version: 1.0.1`.
  A page titled 1.1.0 whose own raw data says 1.0.1 is not publishable as-is — see the open
  question below.

### Open — needs the user

1. **Tag and bump 1.1.0 from `5b527ec`?** That makes the version string, the record and the data
   agree with no re-run. Alternatives: label the record by commit, or carry an explicit
   "measured at `5b527ec`, released as 1.1.0" provenance line and leave the raw field honest.
2. **Is anything still due to land in `flow` or `core` before the tag?** A compute-path change
   forces the affected ladders to re-run; an inert one (the core pointer delta is precedent) does
   not.

### Next action

Wait for the 4-GPU pilot rung — the first multi-GPU run on this build and so the first exercise of
the halo path — then release `weak`, `strong-gpu`, `strong-cpu`, `tgv`, `march`, `spread`, `levels`.

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
