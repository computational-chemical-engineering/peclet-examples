"""Plane Poiseuille flow with peclet's cut-cell immersed-boundary flow solver.

This drives the *real* `peclet.flow` solver: a body force pushes fluid down a
channel whose no-slip walls are defined by a signed distance function (SDF) and
resolved with the Robust-Scaled cut-cell IBM. The steady centreline velocity is
compared with the analytic parabola ``U_max = F H^2 / (8 mu)`` and the error is
tracked under grid refinement.

It is the solver-backed sequel to the pure-NumPy ``mms`` warm-up: same physics,
now with immersed walls that do not align with the grid (the walls sit at
non-integer ``y`` so most wall cells are cut).
"""

from __future__ import annotations

import os
import sys

import numpy as np


def _import_flow():
    """Import ``peclet.flow``.

    In a normal install this is just ``from peclet import flow``. For local
    authoring against a source build of the suite, set ``PECLET_LOCAL_BUILD`` to
    a flow build directory (e.g. ``.../flow/build_mpi``) and it is added to the
    path — so the gallery can be rendered without a wheel installed.
    """
    try:
        from peclet import flow
        return flow
    except ImportError:
        local = os.environ.get("PECLET_LOCAL_BUILD")
        if local and local not in sys.path:
            sys.path.insert(0, local)
        from peclet import flow  # retry (raises a clear ImportError if still missing)
        return flow


def channel_sdf(nx: int, ny: int, nz: int, ylo: float, yhi: float) -> np.ndarray:
    """Global SDF ``sdf[x, y, z]``; negative inside the solid walls (peclet's sign convention)."""
    gy = np.arange(ny, dtype=np.float64)
    sdf = np.empty((nx, ny, nz))
    sdf[:, :, :] = np.minimum(gy - ylo, yhi - gy)[None, :, None]
    return sdf


def solve(N: int, *, rho=1.0, mu=0.1, dt=50.0, F=0.01, max_steps=400):
    """Run one body-force Poiseuille case at wall-to-wall resolution ``N``.

    Returns
    -------
    dict with the wall half-gap ``H``, the full cross-channel velocity profile
    ``y``/``u`` at steady state, the simulated and analytic peak velocities, and
    the percentage error.
    """
    flow = _import_flow()

    nx, nz = 8, 8
    ny = N
    ylo = round(0.30 * ny) + 0.5  # non-integer walls -> cut cells
    yhi = round(0.70 * ny) + 0.5
    H = yhi - ylo

    s = flow.Solver(nx, ny, nz)
    s.set_rho(rho)
    s.set_mu(mu)
    s.set_dt(dt)
    s.set_body_force(F, 0.0, 0.0)                 # force per unit volume (= -dp/dx)
    s.set_velocity_solver_params(200)             # IBM RB-GS velocity solve
    s.set_pressure_solver_params(1)               # x-independent flow: projection is a no-op
    s.set_solid(channel_sdf(nx, ny, nz, ylo, yhi), cutcell_pressure=False)

    prev = 0.0
    for it in range(max_steps):
        s.step()
        u = s.get_u()                             # collective gather: all ranks must call
        stop = False
        if s.rank() == 0:
            u_now = float(u.max())
            stop = it > 5 and abs(u_now - prev) < 1e-7 * (abs(u_now) + 1e-12)
            prev = u_now
        if s.bcast_from_root(stop):
            break

    u = s.get_u()
    _ = s.get_p()
    if s.rank() != 0:
        return None

    # Cross-channel velocity profile at mid-span, and the peak velocity.
    prof = u[nx // 2, :, nz // 2]
    y = np.arange(ny, dtype=np.float64)
    U_sim = float(u.max())
    U_ana = F * H * H / (8.0 * mu)
    err = 100.0 * abs(U_sim - U_ana) / U_ana
    return dict(N=ny, H=H, ylo=ylo, yhi=yhi, y=y, u=prof,
                U_sim=U_sim, U_ana=U_ana, err=err, F=F, mu=mu)


def convergence(Ns=(16, 32, 64), **kw):
    """Return a list of per-resolution result dicts (root rank) for a refinement study."""
    return [solve(int(N), **kw) for N in Ns]
