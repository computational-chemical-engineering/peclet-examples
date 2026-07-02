"""Channel momentum balance: the Method of Manufactured Solutions (MMS).

This is the *shared computation* imported by both the Quarto and the Jupyter Book
versions of the example, so the two galleries render byte-identical numbers and
figures and differ only in the authoring/build tooling.

Physics & the MMS idea
----------------------
Steady, fully developed flow in a channel of height ``H`` reduces the streamwise
momentum equation to a 1-D ODE for the velocity profile ``u(y)``::

    mu u''(y) = -f(y),     u(0) = u(H) = 0   (no-slip)

For a *constant* body force ``f = G = -dp/dx`` this is classic plane Poiseuille
flow with the parabolic solution ``u = G/(2 mu) y (H - y)``. That case is a poor
convergence test, though: a second-order central difference is *exact* for
quadratics, so the discrete error is machine zero at every resolution.

The Method of Manufactured Solutions fixes this. We *choose* a smooth target
profile that satisfies the no-slip walls,

    u_exact(y) = U0 * sin(pi y / H),

analytically differentiate it to find the body force that produces it,

    f(y) = -mu u_exact'' = mu U0 (pi/H)^2 sin(pi y / H),

feed that ``f`` to the solver, and compare. Because the solution is no longer a
low-order polynomial, the finite-difference error now decays at the scheme's
true rate, O(h^2) -- exactly the analytical-validation pattern `peclet`'s flow
solver uses (cf. ``flow/scripts/verify_poiseuille_sdflow.py``).
"""

from __future__ import annotations

import numpy as np


def u_exact(y: np.ndarray, *, U0: float, H: float) -> np.ndarray:
    """Manufactured velocity profile u(y) = U0 sin(pi y / H)."""
    return U0 * np.sin(np.pi * y / H)


def body_force(y: np.ndarray, *, U0: float, mu: float, H: float) -> np.ndarray:
    """Body force f(y) whose ODE solution is exactly ``u_exact``."""
    return mu * U0 * (np.pi / H) ** 2 * np.sin(np.pi * y / H)


def solve_fd(N: int, *, U0: float, mu: float, H: float):
    """Solve mu u'' = -f(y) on [0, H] with N interior points (Dirichlet no-slip).

    Returns
    -------
    y : (N+2,) grid including both walls
    u : (N+2,) finite-difference velocity, with u[0] = u[-1] = 0
    """
    y = np.linspace(0.0, H, N + 2)
    h = y[1] - y[0]

    # Tridiagonal system A u = b for the interior unknowns.
    # Central difference of u'': (u[i-1] - 2 u[i] + u[i+1]) / h^2 = -f/mu
    main = -2.0 * np.ones(N)
    off = np.ones(N - 1)
    A = (np.diag(main) + np.diag(off, 1) + np.diag(off, -1)) / h**2
    b = -body_force(y[1:-1], U0=U0, mu=mu, H=H) / mu

    u_interior = np.linalg.solve(A, b)
    u = np.concatenate(([0.0], u_interior, [0.0]))
    return y, u


def max_error(N: int, *, U0: float, mu: float, H: float) -> float:
    """Max-norm error of the FD solve against the manufactured profile."""
    y, u = solve_fd(N, U0=U0, mu=mu, H=H)
    return float(np.max(np.abs(u - u_exact(y, U0=U0, H=H))))


def convergence(Ns, *, U0: float, mu: float, H: float):
    """Return (Ns, errors) for a grid-refinement study."""
    Ns = np.asarray(list(Ns), dtype=int)
    errs = np.array([max_error(int(N), U0=U0, mu=mu, H=H) for N in Ns])
    return Ns, errs
