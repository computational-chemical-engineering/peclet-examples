# Correctness gates

## bed: u_mean after 13 steps from rest, h = 0.0555556, MG depth 4, velocity multigrid off

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| bed_weak_gpu8_levels4 | 8 | h100 | 453.0 M | 1.638889605551e-04 | 0.00e+00 |

**SINGLE RUN** — nothing to compare it against yet.

## bed: u_mean after 13 steps from rest, h = 0.0555556, MG depth 10, velocity multigrid off

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| bed_strong_gpu1 | 1 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_gpu1_pilot | 1 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu1 | 1 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu1_march | 1 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_gpu2 | 2 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu2 | 2 | h100 | 113.2 M | 1.638889605660e-04 | 6.75e-11 |
| bed_strong_gpu4 | 4 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu4 | 4 | h100 | 226.5 M | 1.638889605620e-04 | 4.34e-11 |
| bed_weak_gpu4_march | 4 | h100 | 226.5 M | 1.638889605620e-04 | 4.34e-11 |
| bed_weak_gpu4_pilot | 4 | h100 | 226.5 M | 1.638889605620e-04 | 4.34e-11 |
| bed_strong_gpu8 | 8 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_gpu8_r2 | 8 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu8 | 8 | h100 | 453.0 M | 1.638889605686e-04 | 8.38e-11 |
| bed_weak_gpu8_march | 8 | h100 | 453.0 M | 1.638889605686e-04 | 8.38e-11 |
| bed_strong_gpu16 | 16 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_gpu16_r2 | 16 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu16 | 16 | h100 | 906.0 M | 1.638889605676e-04 | 7.77e-11 |
| bed_weak_gpu16_march | 16 | h100 | 906.0 M | 1.638889605676e-04 | 7.77e-11 |
| bed_strong_cpu24 | 24 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_gpu32 | 32 | h100 | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_weak_gpu32 | 32 | h100 | 1811.9 M | 1.638889605647e-04 | 5.94e-11 |
| bed_weak_gpu32_march | 32 | h100 | 1811.9 M | 1.638889605647e-04 | 5.94e-11 |
| bed_weak_gpu32_r2 | 32 | h100 | 1811.9 M | 1.638889605647e-04 | 5.94e-11 |
| bed_weak_gpu32_r3 | 32 | h100 | 1811.9 M | 1.638889605647e-04 | 5.94e-11 |
| bed_strong_cpu48 | 48 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_cpu96 | 96 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_cpu192 | 192 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_cpu192_pilot | 192 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_cpu384 | 384 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |
| bed_strong_cpu768 | 768 | genoa | 56.6 M | 1.638889605549e-04 | 0.00e+00 |

**PASS** — worst relative deviation 8.38e-11 across 30 runs, 1 to 768 ranks, 2 machine(s).

## bed: u_mean after 13 steps from rest, h = 0.0555556, MG depth 10, velocity multigrid on

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| bed_strong_cpu1536 | 1536 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu1536_r2 | 1536 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |
| bed_strong_cpu1536_r3 | 1536 | genoa | 56.6 M | 1.638890208586e-04 | 0.00e+00 |

**PASS** — worst relative deviation 0.00e+00 across 3 runs, 1536 to 1536 ranks, 1 machine(s).

## tgv: ke_mean after 13 steps from rest, h = 0.0981748, MG depth 10, velocity multigrid off

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| tgv_weak_gpu1 | 1 | h100 | 56.6 M | 2.981944304649e-03 | 0.00e+00 |
| tgv_weak_gpu4 | 4 | h100 | 226.5 M | 2.981944304649e-03 | 0.00e+00 |
| tgv_weak_gpu16 | 16 | h100 | 906.0 M | 2.981944304649e-03 | 1.45e-16 |
| tgv_weak_gpu32 | 32 | h100 | 1811.9 M | 2.981944304649e-03 | 1.45e-16 |
| tgv_strong_cpu192 | 192 | genoa | 56.6 M | 2.981944304649e-03 | 1.45e-16 |
| tgv_strong_cpu768 | 768 | genoa | 56.6 M | 2.981944304649e-03 | 1.45e-16 |

**PASS** — worst relative deviation 1.45e-16 across 6 runs, 1 to 768 ranks, 2 machine(s).

## tgv: ke_mean after 13 steps from rest, h = 0.0981748, MG depth 10, velocity multigrid on

| run | ranks | machine | cells | value | rel. dev. |
|---|---:|---|---:|---:|---:|
| tgv_strong_cpu1536 | 1536 | genoa | 56.6 M | 2.981908755561e-03 | 0.00e+00 |

**SINGLE RUN** — nothing to compare it against yet.

## Between configurations (not a gate — a measurement)

peclet 1.0.0 selects the momentum solver from the per-rank workload (`set_velocity_multigrid_auto`, on below ~65k cells/rank) and the multigrid depth is a study parameter. Runs that differ in either are different computations; this is how far apart their answers land.

| case | configuration | runs | value | vs. first |
|---|---|---:|---:|---:|
| bed | MG depth 4, velocity MG off | 1 | 1.638889605551e-04 | — |
| bed | MG depth 10, velocity MG off | 30 | 1.638889605549e-04 | 9.97e-13 |
| bed | MG depth 10, velocity MG on | 3 | 1.638890208586e-04 | 3.68e-07 |
| tgv | MG depth 10, velocity MG off | 6 | 2.981944304649e-03 | — |
| tgv | MG depth 10, velocity MG on | 1 | 2.981908755561e-03 | 1.19e-05 |

## Sampled solid fraction vs the packing

Worst deviation 0.0000 over 34 runs (the driver refuses to run past 0.02). **PASS**

## Pressure solve converged (never at its iteration cap)

**PASS** — worst iteration count 33 against a cap of 200.

## Weak ladder: every rank owns an identical block

**PASS** — uniform at all 19 weak rungs.

