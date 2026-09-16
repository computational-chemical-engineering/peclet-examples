# peclet 1.1.0 scaling campaign — state

*Rewritten in place at every milestone. A position, not a diary.*

## Objective

Replace the 1.0.0 scaling record (page + unpublished Zenodo deposit) with one measuring the
**1.1.0** implementation only. **No historic data from previous implementations appears in the
page or the dataset** (user directive, 2026-09-16) — this is a record of one version, not a
comparison.

## What "1.1.0" is

**Not tagged yet.** Every package reads 1.0.1; `v1.0.0` and `v1.0.1` are the only 1.x tags.
The campaign pins the commits that are slated to become 1.1.0, all clean and pushed:

| repo | commit | subject |
|---|---|---|
| core | `1974422` | style: clang-format the four files the blocking Quality job rejects |
| morton | `6e8abef` | peclet-morton 1.0.1 |
| flow | `d05eb15` | flow: gate the open-face fix on the COLLOCATED grid too (SCALING_ISSUES #3/#8) |

If 1.1.0 is tagged from exactly these commits the record is 1.1.0 as measured. If more lands
first, either the record states the delta or the affected ladders re-run. **Confirm before the
deposit is published.**

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

**Harness ported, builds provisioning.** No ladder submitted yet, no measurement spent.

Pinned ref: **umbrella `5b527ec`** (one ref for the whole build). Its recorded core pointer is one
commit behind core's HEAD, and that commit (`1974422`) is clang-format reflowing comments only —
verified semantically inert — so the pin is exact for the compute code.

| step | state |
|---|---|
| `install_bench.sh` takes a tag, branch **or SHA** (`--detach`), name decorates the paths | done |
| campaign dir staged at `/projects/0/prjs1022/peclet/bench-1.1.0` | done |
| CPU build (`26802070`, genoa) | RUNNING — compiling flow |
| GPU build (`26802061`, gpu_h100) | PENDING (priority) |
| driver records the momentum solver **by name** (`velocity_solver()`, new in 1.1.0) | done |
| `analyze.py` stripped of the companion pinned-solver campaign + the overlay figure | done |
| `index.qmd.in` stripped of every 1.0.0 amendment (337 → 193 lines, no historic reference) | done |
| Zenodo metadata rewritten for 1.1.0, deposit/report renamed | done |

### API compatibility, checked before spending anything

The 1.0.0 driver runs unmodified on 1.1.0: every method it calls still exists
(`set_pressure_multigrid`, `set_solid`, `set_body_force`, `diagnostics.*`,
`pressure_telescope`, `max_open_divergence`). `set_velocity_chebyshev` was removed, but it never
shipped in 1.0.0 and the driver never called it. `checkSealedInflowCells` (new, throws at
`set_solid`) cannot fire here: it needs an inflow face, and this case is triply periodic.

**What changes the numbers:** the momentum solver. 1.1.0 selects on
kappa = 1 + 4·dt·mu·(w_x+w_y+w_z)/rho, V-cycle at kappa >= 13, decided at the head of the first
`step()`. This case runs at D = 6 → **kappa = 73**, so every rung takes the V-cycle — and the rule
is **rank-independent**, so unlike 1.0.0 there is no mid-ladder algorithm change. Pressure MG
default is still 4 levels, so the one stated departure (depth as deep as the grid admits) carries
over unchanged.

### Two sections of the page are deliberately unwritten

`index.qmd.in` carries `%%SOLVER_SELECTION_SECTION%%` and `%%STRONG_GPU_ANOMALY_SECTION%%`. Both
replaced passages every number of which was a 1.0.0 measurement (the mid-ladder solver switch; the
16-GPU anomaly and its withdrawn hypothesis). Whether 1.1.0 shows either is a question for the new
data, so they are written FROM the results, not carried across.

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
