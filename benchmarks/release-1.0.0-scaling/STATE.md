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

- Site builds done, one tree per backend (`$PROJ/suite-v1.0.0-bench-{h100,cpu}`), censuses pulled
  into the artifact. flow 1.0.0, `has_mpi=True`, Cuda and OpenMP.
- **Pilot passed, including the memory-fit gate**: 384³ = 56.6 M cells on ONE H100 with the fp64
  operator default, 4.0 s/step, 29.7 pressure iterations, `max|div|` 2.7e-14. The 1.81-Gcell top
  rung is therefore on; the 320³ fallback is not needed.
- All ladders queued and largely complete; the permeability march converges in **40 steps**, so it
  runs across the whole weak ladder rather than at three points.
- Analysis, generated page and deposit packaging written and committed.

## Next action

1. Drain the queue, pull results, `python analyze.py results && python render_page.py`.
2. Eyeball the figures, add the card to `benchmarks/index.qmd`, commit results.
3. Package the deposit; **ask before any Zenodo upload** (a draft is reversible, publishing is not).
4. After the DOI exists: swap `PecletBenchmarks` in MORPHO (`morpho-application-M1.tex:240-247`,
   a TODO the proposal already carries) and re-check the sentence's two numbers.

## Gates

| Gate | Value | Status |
|---|---|---|
| 384³/GPU fits in 94 GB with fp64 operators | 4.0 s/step on one H100 | **PASS** |
| ⟨u⟩ agrees across every rung and both machines | worst 8e−11; exactly 0 between 1 H100 and 384 cores | **PASS** |
| φ_voxel vs packing φ, every run | 0.4500 vs 0.4500 | **PASS** |
| pressure iterations flat across the weak ladder | 29.7 → 30.0 through 8 GPUs | passing so far |
| blocks uniform on the weak ladder | uniform at every rung | **PASS** |
| pressure solve never at its cap | worst 33 of 200 | **PASS** |

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
