# Parallel performance of peclet.flow {{flow_version}}

Measurement data and reproduction scripts for the parallel performance of
[`peclet.flow`]({{doi_flow}}) {{flow_version}} solving **creeping flow through a periodic random
sphere packing with the cut-cell immersed boundary method**.

A rendered version of the report is the gallery page linked from this record; the same report is
included here as HTML and PDF. *(Zenodo serves uploaded HTML as plain text, so download
`peclet-flow-{{flow_version}}-scaling-report.html` and open it locally — it is self-contained,
figures included.)*

## Scope

This record measures **one implementation**. It reports peclet.flow {{flow_version}} and contains no
data from any earlier version: it states what this release does, not how it compares with its
predecessors.

## The case

1043 spheres of radius *R* = 1 at solid fraction φ = {{phi}} in a triply periodic cubic box of
21.333 *R*, resolved at 384³ cells so *R* = {{r_cells}} cells — {{cells_per_gpu_m}} M cells, which is
what one H100 holds. Flow is driven by a body force; advection is off. One MPI rank per GPU or core.

Four ladders on one case: **weak** (384³ cells per GPU, 1 → {{w_top_n}} H100, the unit cell tiled),
**strong** on CPU ({{s_base_n}} → {{s_top_n}} Genoa cores) and on GPU (1 → {{w_top_n}} H100), and a
geometry-free Taylor–Green control on the same grids.

## Headline results

| | |
|---|---|
| Weak scaling, {{w_top_n}} H100 @ {{w_top_gcells}} G cells | {{w_base_per}} → {{w_top_per}} Mcell/s per GPU — **{{w_weak_eff}} % efficiency** |
| Pressure iterations across that ladder | {{w_base_iters}} → {{w_top_iters}} (flat) |
| Strong scaling, {{s_base_n}} → {{s_top_n}} cores | {{s_base_s}} s → **{{s_top_s}} s**, {{s_speedup}}× — {{s_strong_eff}} % of ideal |
| Strong scaling, 1 → {{w_top_n}} H100 | {{t_base_s}} s → {{t_top_s}} s, {{t_speedup}}× |
| Geometry-free control, weak | {{wt_weak_eff}} % |
| Permeability | k/R² = {{k_over_R2}}, {{k_runs}} rungs, spread {{k_spread}} |

**Correctness before speed.** Every run starts from rest and takes the same steps, so ⟨u⟩ is a
single number every rung must reproduce: **{{gate_value}}**, worst relative deviation
**{{gate_worst}}** over {{gate_runs}} runs from 1 to {{gate_max_ranks}} ranks, across both the CUDA
and the OpenMP backend. The control is tighter still, {{tgv_gate_worst}}.

One momentum solver runs at every rung. {{flow_version}} selects it from the implicit-diffusion
operator's condition number, κ = 1 + 12·D, taking the velocity multigrid at κ ≥ 13; this case runs at
D = {{diff_number}}, so κ = {{kappa}}, and the criterion does not depend on the rank count. Every run
records the solver it used — all report `{{solver_name}}`.

## Configuration

Shipped {{flow_version}} defaults, with **one stated exception**: the pressure multigrid is asked for
as much depth as the grid admits rather than the default four levels, because depth is a property of
the grid. The cost of the default is measured, not argued — the same {{levels4_n}}-GPU weak rung at
four levels takes **{{levels4_ms}} ms per step against {{levels10_ms}} ms** at full depth
({{levels4_ratio}}), at an unchanged iteration count. That run is included and excluded from every
ladder. Halo transport is left to the shipped auto-detection, which chose: {{halo_path}}.

## What is in the archive

`peclet-flow-{{flow_version}}-scaling.tar.gz` contains the complete campaign directory:

- `scaling_bench.py` — the driver; `make_bed.py` and `bed_phi0.45_r18_s0.npz` — the geometry
- `snellius/` — site build and job scripts (`install_bench.sh`, `submit_ladders.sh`, `run_{gpu,cpu}.sh`)
- `results/snellius-{h100,genoa}/*.json` — every raw run, with its `.log` beside it
- `analyze.py` → `summary.md`, `gates.md`, `headline.json`, the figures
- `README.md` (the runbook), `DECISIONS.md` (what was chosen and rejected), `STATE.md`
- `hierarchy_predict.txt` — the decomposition evidence, reproducible without a cluster

`census-h100.txt` / `census-cpu.txt` record the toolchain, MPI, driver and wheel checksums for each
machine. `MANIFEST.sha256` covers every file in this record; `PROVENANCE.txt` pins the commits.

## Reproduce

```bash
tar xzf peclet-flow-{{flow_version}}-scaling.tar.gz && cd release-{{flow_version}}-scaling
sbatch --nodes=1 --gpus-per-node=1 --ntasks-per-node=1 snellius/install_bench.sh v{{flow_version}} h100
sbatch -p genoa --gpus-per-node=0 -c 32 -t 02:00:00    snellius/install_bench.sh v{{flow_version}} cpu
export EXPECT_FLOW_VERSION={{flow_version}}      # a run refuses a build that is not this version
./snellius/submit_ladders.sh weak                # and strong-gpu, strong-cpu, tgv, march, spread, levels
python analyze.py results                        # tables, gates, figures
```

The published wheels cannot run this: MPI is a build-time option in `flow` and the PyPI wheels are
single-rank, so the study builds the released tag from source, one tree per backend.

## A known anomaly, reported rather than smoothed

On the GPU strong ladder the 16-GPU rung takes 1349 ms against 574 ms at 8 and 539 ms at 32 — 2.3×
slower than both neighbours, and reproducible across four allocations (spread 1.02×). It is **not**
convergence: momentum sweeps (29) and pressure iterations (29.7) are identical at all three rungs, so
the same work simply executes more slowly. Decomposition shape is ruled out on this record's own
data — surface-to-volume is monotone across the three rungs and the worst-shaped one is the fastest.
It is real, reproducible, confined to one rank count, and undiagnosed.

## Licence and citation

Measurement data: **CC-BY-4.0**. Scripts: **MIT**, as the `peclet-examples` repository.
Cite this record's **concept DOI** so the reference follows later campaigns, and cite the software
separately.

Runs were performed on the Dutch national supercomputer **Snellius** (SURF).
