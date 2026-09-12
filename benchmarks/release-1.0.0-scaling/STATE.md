# peclet 1.0.0 scaling deposit — campaign state

*Rewritten in place at every milestone. A position, not a diary; the history is in `DECISIONS.log`.*

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

- Driver, bed generator, provisioning and rung scripts written; driver validated against an API
  stub at np=1,2,4 (tiling exact, φ_voxel 0.4499 vs 0.4500 at every tiling).
- Bed artifact grown and gated (overlap 0, independent voxel fraction 0.4553 vs 0.4500 analytic).
- Snellius site builds of `v1.0.0` **in flight**: jobs 26628297 (h100), 26628298 (cpu),
  one tree per backend under `$PROJ/suite-v1.0.0-bench-<target>`.

## Next action

1. When the h100 venv lands: **pilot** — 1 GPU bed strong (memory-fit gate at 56.6 M cells/GPU with
   the fp64 operator default), then 4 GPUs weak. Then the CPU pilot at 192 ranks.
2. Full ladders, top rung repeated for the allocation-spread control.
3. Analysis + plots + `index.qmd` + standalone report; then the Zenodo deposit.

## Gates

| Gate | Value | Status |
|---|---|---|
| 384³/GPU fits in 94 GB with fp64 operators | — | **pilot** (fallback 320³/GPU = 1.05 Gcells) |
| ⟨u⟩ agrees across every rung | — | pending |
| φ_voxel vs packing φ, every run | 0.4499 vs 0.4500 (stub) | passing |
| pressure iterations flat across the weak ladder | — | pending |
| blocks uniform on the weak ladder | true at np=1,2,4 (stub) | pending on real ORB |

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
