# Momentum-solver campaign — state

Rewritten in place. History goes to DECISIONS.md, which is append-only.

## Objective (user, 2026-09-14)

1. Implement a **Chebyshev momentum smoother** and test whether it gives the expected win.
2. Run an **MPI-CPU scaling ladder** for the best momentum solver, **pinned at every rank count**
   (1.0.0 leaves it to `setSolidVelocityMgAuto`, which switches below 65536 cells/rank — so only
   the top rung crosses the threshold and that ladder changes algorithm there).
3. Follow-up: **Chebyshev as the MG smoother**.

## Answer to (2) — COMPLETE. Pin the velocity V-cycle at every rank count.

384³ fixed, genoa, same rungs as the 1.0.0 deposit:

| cores | cells/rank | RB-GS ms | V-cycle ms | V-cycle wins | RB-GS it/cmpt | V-cycle it/cmpt |
|---:|---:|---:|---:|---:|---:|---:|
| 24 | 2 359 296 | 70890 | 36176 | 1.96x | 200 = CAP | 9.7 |
| 48 | 1 179 648 | 48823 | 23255 | 2.10x | 200 = CAP | 9.7 |
| 96 | 589 824 | 25681 | 12064 | 2.13x | 200 = CAP | 9.7 |
| 192 | 294 912 | 18434 | 8395 | 2.20x | 200 = CAP | 9.7 |
| 384 | 147 456 | 8130 | 3646 | **2.23x** | 200 = CAP | 9.7 |
| 768 | 73 728 | 2904 | 1745 | 1.66x | 200 = CAP | 9.7 |
| 1536 | 36 864 | 1298 | 876 | 1.48x | 200 = CAP | 9.7 |

(The 1536 row is the 1.0.1 same-binary pair. The 1.0.0 `vmgon` run at that rung came in at 1891 ms
— a 2.16x spread on identical config, the known 1536-rank placement spread. Repeats queued.)

Three findings that outlive the campaign:

- **The auto rule has the sign of the effect backwards.** It switches MG *on* below 65536
  cells/rank, but the V-cycle's advantage is LARGEST at big blocks (2.23x at 147k) and SMALLEST at
  small ones (1.48x at 37k). The threshold should be removed for this operator class, not retuned.
- **Red-black never converges here**: 200.0 sweeps/component at every rung = `velIters_`. The
  deposit's RB-GS rungs measured a capped solve, which is also the source of its 3.7e-07 gate
  disagreement "between configurations".
- **The deposit's 122 %-of-ideal was the algorithm switch.** Pinned: RB-GS 54.6x on 64x the cores
  (85 %), V-cycle 41.3x (65 %). Both are honest scaling of ONE algorithm.

## Answer to (1) — Chebyshev works, and crosses over against the V-cycle as blocks shrink

`flow` branch `cheb-momentum`, commit `6773b32`. Gershgorin interval, no power iteration.

| | 96³ np=2 (442k/rank) | 192 cores (295k/rank) | 768 cores (74k/rank) |
|---|---:|---:|---:|
| RB-GS momentum ms | 3730 | 14675 | 2156 |
| Chebyshev momentum ms | 2528 | 6238 | **891.5** |
| V-cycle momentum ms | 1783 | 4472 | 907.4 |

√κ theory predicted 111 iterations/component; measured 107 (RB-GS: 147). At 768 cores Chebyshev's
momentum phase is 1.8 % FASTER than the V-cycle's, having been 39 % slower at 192 — the predicted
latency crossover. 1536 rung queued. ⟨u⟩ identical to the V-cycle's converged value.

## Answer to (3) — Chebyshev as the MG smoother: NO at this configuration

Commit `93d9dcb`. V-cycles/component (lower = stronger smoother), 96³ np=2:

| degree \ ratio | 3 | 4 | 6 |
|---:|---:|---:|---:|
| 2 | 17.3 | 15.3 | 14.3 |
| 3 | 12.7 | 11.0 | 10.0 |
| 4 | 10.0 | 9.0 | **8.0** |
| 6 | 8.0 | 7.0 | 6.0 |

Red-black 2+2: 9.3 cycles, momentum 1778 ms. Best Chebyshev (deg 4, ratio 6): 8.0 cycles, 2143 ms
— a stronger smoother per cycle that still loses 1.21x on wall time. **The exchange saving is not
real once degree is matched for smoothing strength**: degree 2 costs 2 exchanges against 2 RB-GS
sweeps' 4 but is much weaker (14.3 cycles); degree 4, which is not weaker, costs the same 4. What
remains is that Chebyshev needs two kernel passes (residual, then update) where a Gauss-Seidel
sweep fuses read and update into one. Only deg 2 / ratio 6 has a genuine exchange saving (172/cmpt
vs 223, −23 %) — queued at 768 and 1536 cores, where exchanges dominate.

## GPU A/B — the deposit's GPU rungs are capped too (2026-09-15)

| H100 | RB-GS | V-cycle | ratio | RB-GS it/cmpt |
|---|---:|---:|---:|---:|
| 1 GPU step ms | 4025 | 1840 | 2.19x | 200 = CAP |
| 1 GPU momentum ms | 3012 | 828 | 3.64x | |
| 4 GPU step ms | 1203 | 664 | 1.81x | 200 = CAP |

The pinned-off 1-GPU run reproduces the deposit's own `bed_strong_gpu1` rung to 1.0006x, so it IS
that rung — the identification is measured, not inferred.

## Chebyshev at the small-block end (2026-09-15)

1536 cores (36 864 cells/rank), single allocations on a rung whose repeats spread 2.01x:
`cheb` momentum **443 ms** against the five V-cycle allocations' 473 / 518 / 580 / 627 / 1037 ms —
below all of them. Suggestive of the predicted crossover, NOT conclusive at one allocation on this
rung. `mgcheb` never wins: 1017.9 (d2r6) / 1226.8 (d4r6) against `cheb` 934.5 at 1536, and 1719.4
(d4r6) against `on` 1745.3 at 768 — a 1.5 % edge, inside the noise.

## Next action

1. DONE — all 14 jobs ran; results synced and committed.
2. If the Chebyshev crossover is to be claimed rather than suggested, it needs repeat allocations
   at 1536 (that rung's spread is 2.01x, so one allocation decides nothing).
3. Decide whether Chebyshev ships as anything other than an option. The V-cycle is the default
   recommendation regardless, on both machines.

## Gates — all green

- flow `tests/kokkos_mpi`: **106/106** on `93d9dcb` (run in 4 chunks; this box has one core).
- ⟨u⟩ across solvers: 8e-12 (RB-GS / Chebyshev / V-cycle / MG-Chebyshev all agree at 96³).
- `max|div|` after projection: 4.6e-14, solver-independent.

## Open, needs the user

- Changing the shipped `vmgAutoCells_ = 65536` threshold, or defaulting to the V-cycle outright.
  The measurement is unambiguous but a shipped default is a 1.1 release decision and moves every
  existing user's numbers by the momentum tolerance.
- Whether the 1.0.0 deposit's text should be amended now that its RB-GS rungs are known to have
  been running a capped momentum solve.

## Anchors

- `flow/src/mac_cheb_momentum.hpp` — bounds, update kernel, coefficient recurrence
- `flow/src/flow_ibm_core.hpp:1290` `chebSolveComp`; dispatch `:1483`
- `flow/src/mac_velocity_mg.hpp` `chebSmooth` + per-solve bounds in `solve()`
- `flow/src/flow_ibm_geometry.hpp:230` `setSolidVelocityMgAuto` — the threshold rule
- `flow/src/flow_ibm.hpp:4273` `velIters_ = 200` — the cap RB-GS hits
- Snellius `/projects/0/prjs1022/peclet/`: `bench-momentum` (campaign), `bench-cheb-venv` (1.0.1 +
  Chebyshev), `flow-cheb-src` (rsync'd source), `suite-v1.0.0-bench-cpu/.venv` (the 1.0.0 ladders)
