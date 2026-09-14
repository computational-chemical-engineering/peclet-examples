# Momentum-solver campaign — decision log (append-only)

2026-09-14  New campaign directory instead of editing the 1.0.0 deposit's scripts.
  Rejected: an additive, default-off `VMG` knob in `release-1.0.0-scaling/scaling_bench.py`.
  Reason: the deposit is a citable frozen record whose Zenodo tarball is already built; a later
  edit makes the tarball and the repository diverge even when the default path is unchanged.
  Reversible by: deleting `benchmarks/momentum-solver/`.

2026-09-14  The pinned-solver ladder was submitted BEFORE the Chebyshev solver existed.
  Rejected: wait for Chebyshev and run one combined ladder.
  Reason: the ladder needs no code change, it answers the user's "fix the solver for all ranks"
  for the solvers that ship today, and queue time is the long pole in a 2-hour window.
  Reversible by: the ladders are independent jobs.

2026-09-14  Chebyshev treated as Opus engineering, not a Fable design pass.
  Reason: flow already ships a Chebyshev PRESSURE driver to copy, and the momentum operator's
  spectral interval is analytic/Gershgorin rather than something to be estimated — so this is an
  existing pattern applied to a well-conditioned operator, not a new algorithm.
  Reversible by: escalating if the Gershgorin interval had failed with cut cells. It did not.

2026-09-14  The spectral interval is Gershgorin arithmetic on the stored stencil, NOT a power
  iteration (which is what the pressure Chebyshev driver uses, via `estimateEigenvalues`).
  Rejected: reuse `estimateEigenvalues`.
  Reason: a power iteration costs sweeps and can UNDER-estimate lambda_max, which is the one
  error that makes Chebyshev diverge rather than merely converge slowly. Gershgorin is exact
  arithmetic on the coefficients, one reduction, and is a rigorous bound on both sides.
  Evidence: predicted 111 iterations/component from the interval, measured 107.

2026-09-14  Chebyshev is wired into the IBM/periodic path only.
  Reason: the collocated, mixed, `bcStencilPath` and domain-BC branches each own a ghost fold
  that the red-black smoother re-imposes per colour; reproducing that under a polynomial
  iteration is a separate piece of work and none of it is needed for the question asked.
  Reversible by: the dispatch is one `if` at `flow_ibm_core.hpp:1483`.

2026-09-14  Chebyshev's stop keeps the round-off floor but DROPS velSweepLoop's stagnation
  guard ("stop when the residual has not decreased since the last check").
  Reason: Chebyshev minimises a polynomial over the spectral interval, so its max-norm residual
  is NOT monotone — it rises for the first few iterations. The inherited guard aborted the solve
  after three iterations per component and left <u> 3.9 % off the red-black answer. Found by the
  cross-solver <u> gate, which is exactly what that gate is for.

2026-09-14  Snellius Chebyshev test built into its OWN venv (`bench-cheb-venv`) from an rsync'd
  source tree (`flow-cheb-src`), reusing the 1.0.0 tree's Kokkos prefix and morton/core wheels.
  Rejected: push the branch and re-run `install_bench.sh`; or rebuild into the 1.0.0 venv.
  Reason: the 1.0.0 CPU venv is being used by the ladder jobs running right now and must not be
  rewritten under them; `install_bench.sh` would re-clone and rebuild Kokkos for no gain.
  Reversible by: deleting two directories under `/projects/0/prjs1022/peclet/`.

2026-09-14  NOT TAKEN, needs the user: changing the shipped `vmgAutoCells_ = 65536` threshold,
  or making the velocity V-cycle the default outright. The measurement says the threshold is far
  too low (MG wins 2.20× at 294 912 cells/rank), but a shipped default is a 1.1 release decision
  and it moves every existing user's numbers by the momentum tolerance.

2026-09-14  Chebyshev MG smoother: degree follows the V-cycle's own pre/post/bottom sweep counts
  by default (`degree=0`), and the interval is [hi/eig_ratio, hi] rather than the solver's true
  Gershgorin lower bound.
  Reason: a SMOOTHER wants the top of the spectrum because the coarse grid owns the rest; and
  tying degree to the sweep count compares the two smoothers at equal nominal work, which is the
  only comparison that answers the question.

2026-09-14  The per-level Gershgorin reduction runs once per `solve()`, not once per `smooth()`.
  Rejected: bounds inside smooth(), which is where the operator is actually used.
  Reason: per-smooth bounds put an MPI all-reduce on every level of every V-cycle and hand back
  exactly the latency the polynomial smoother exists to save. The operator is fixed for the
  duration of a solve, so once per solve is both correct and cheap.

2026-09-14  The Snellius `bench-cheb-venv` was rebuilt in place while three ladder jobs were still
  pending against it, so those ran on the newer binary (1.0.1 + MG-smoother code) rather than the
  one submitted against.
  Assessed as harmless: the added code is guarded on `chebSmooth_`, default false, so the executed
  path for pins off/on/cheb is unchanged. Noted rather than smoothed over.
