# Correctness gates

## bed: u_mean after 13 steps from rest, h = 0.0555556, MG depth 4, velocity multigrid on

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| bed_weak_gpu8_levels4 | 8 | h100 | 453.0 M | 1.638890208588e-04 | 0.00e+00 |

**SINGLE RUN** — nothing to compare it against yet.

## bed: u_mean after 13 steps from rest, h = 0.0555556, MG depth 10, velocity multigrid on

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| bed_strong_gpu1 | 1 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu1 | 1 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu1_march | 1 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu2 | 2 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu2 | 2 | h100 | 113.2 M | 1.638890208696e-04 | 6.75e-11 |
| bed_strong_gpu4 | 4 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu4 | 4 | h100 | 226.5 M | 1.638890208657e-04 | 4.34e-11 |
| bed_weak_gpu4_pilot | 4 | h100 | 226.5 M | 1.638890208657e-04 | 4.34e-11 |
| bed_strong_gpu8 | 8 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu8_r2 | 8 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu8_sweeps | 8 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu8 | 8 | h100 | 453.0 M | 1.638890208723e-04 | 8.38e-11 |
| bed_weak_gpu8_march | 8 | h100 | 453.0 M | 1.638890208723e-04 | 8.38e-11 |
| bed_strong_gpu16 | 16 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu16_r2 | 16 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu16_r3 | 16 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu16_sweeps | 16 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu16 | 16 | h100 | 906.0 M | 1.638890208713e-04 | 7.77e-11 |
| bed_strong_cpu24 | 24 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu32 | 32 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu32_r2 | 32 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_gpu32_sweeps | 32 | h100 | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_weak_gpu32 | 32 | h100 | 1811.9 M | 1.638890208683e-04 | 5.94e-11 |
| bed_weak_gpu32_march | 32 | h100 | 1811.9 M | 1.638890208683e-04 | 5.94e-11 |
| bed_weak_gpu32_r2 | 32 | h100 | 1811.9 M | 1.638890208683e-04 | 5.94e-11 |
| bed_weak_gpu32_r3 | 32 | h100 | 1811.9 M | 1.638890208683e-04 | 5.94e-11 |
| bed_strong_cpu48 | 48 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu96 | 96 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu192 | 192 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu384 | 384 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu768 | 768 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu1536 | 1536 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu1536_r2 | 1536 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu1536_r3 | 1536 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |

**PASS** — worst relative deviation 8.38e-11 across 34 runs, 1 to 1536 ranks, 2 machine(s).

## tgv: ke_mean after 13 steps from rest, h = 0.0981748, MG depth 10, velocity multigrid on

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| tgv_weak_gpu1 | 1 | h100 | 56.6 M | 2.981908755561e-03 | 0.00e+00 |
| tgv_weak_gpu4 | 4 | h100 | 226.5 M | 2.981908755561e-03 | 0.00e+00 |
| tgv_weak_gpu16 | 16 | h100 | 906.0 M | 2.981908755561e-03 | 1.45e-16 |
| tgv_weak_gpu32 | 32 | h100 | 1811.9 M | 2.981908755561e-03 | 1.45e-16 |
| tgv_strong_cpu192 | 192 | genoa | 56.6 M | 2.981908755561e-03 | 1.45e-16 |
| tgv_strong_cpu768 | 768 | genoa | 56.6 M | 2.981908755561e-03 | 2.91e-16 |
| tgv_strong_cpu1536 | 1536 | genoa | 56.6 M | 2.981908755561e-03 | 1.45e-16 |

**PASS** — worst relative deviation 2.91e-16 across 7 runs, 1 to 1536 ranks, 2 machine(s).

## Between configurations (not a gate — a measurement)

The momentum solver is selected from the operator's condition number and the multigrid depth is a study parameter. Runs that differ in either are different computations; this is how far apart their answers land.

| case | configuration | runs | value | vs. first |
|---|---|---:|---:|---:|
| bed | MG depth 4, velocity MG on | 1 | 1.638890208588e-04 | — |
| bed | MG depth 10, velocity MG on | 34 | 1.638890208586e-04 | 9.97e-13 |

## Sampled solid fraction vs the packing

Worst deviation 0.0000 over 35 runs (the driver refuses to run past 0.02). **PASS**

## Pressure solve converged (never at its iteration cap)

**PASS** — worst iteration count 33 against a cap of 200.

## Weak ladder: every rank owns an identical block

**PASS** — uniform at all 17 weak rungs.

