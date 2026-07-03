#!/usr/bin/env python3
"""Generate bfs_cache.npz for the backward-facing-step example.

Solves the Gartling expansion-ratio-2 BFS at Re_S = 100 and 200 to steady state and stores the
velocity fields + reattachment lengths. Run once (GPU recommended: ~30 min/Re; CPU ~2x) to refresh
the cache the page loads. Uses the local build if PECLET_LOCAL_BUILD is set, else the installed peclet.

    PECLET_LOCAL_BUILD=/path/to/flow/build_cuda python make_cache.py
"""
import os, sys, time
import numpy as np

_local = os.environ.get("PECLET_LOCAL_BUILD")
if _local:
    for p in _local.split(os.pathsep):
        sys.path.insert(0, p)
from peclet import flow


def inlet_profile(H, S, nz, U):
    """Developed parabola over the open upper half [S, 2S], zero over the step face [0, S]."""
    prof = np.zeros((H, nz, 3))
    yc = np.arange(H) + 0.5
    eta = (yc - S) / S
    up = yc > S
    prof[up, :, 0] = (6.0 * U * eta * (1 - eta))[up, None]
    return prof


def reattachment(u_bottom, x_step=0):
    """First reverse->forward crossing of the near-bottom-wall streamwise velocity (end of bubble)."""
    reversed_yet = False
    for i in range(x_step + 1, len(u_bottom)):
        if u_bottom[i] < 0.0:
            reversed_yet = True
        elif reversed_yet and u_bottom[i] >= 0.0:
            return (i - 1) + u_bottom[i - 1] / (u_bottom[i - 1] - u_bottom[i])
    return 0.0


def solve_bfs(Re, S=16, Lr=12, U=1.0, nz=4, dt=0.2, steps=12000):
    """BFS at Re_S = U*S/nu to steady state (fixed step budget past the entrance transient)."""
    H, L = 2 * S, Lr * S
    nu = U * S / Re
    s = flow.Solver(L, H, nz)
    s.set_rho(1.0); s.set_mu(nu); s.set_dt(dt); s.set_advection(True)
    s.set_domain_bc_profile(0, inlet_profile(H, S, nz, U))  # partial parabolic inlet == the step
    s.set_domain_bc(1, 3)                                    # +x outflow
    s.set_domain_bc(2, 1); s.set_domain_bc(3, 1)            # no-slip walls
    s.set_velocity_solver_params(60)
    s.set_pressure_multigrid(True, levels=8)
    s.set_pressure_solver_params(80)
    s.set_pressure_geometry(np.full((L, H, nz), 1e30, order="F"))
    t0 = time.time()
    for it in range(steps):
        s.step()
    u = s.get_u()[:, :, nz // 2]; v = s.get_v()[:, :, nz // 2]
    xr = reattachment(u[:, 0])
    div = s.max_open_divergence()
    print(f"  Re_S={Re:.0f}: {steps} steps in {time.time()-t0:.0f}s  x_r/S={xr/S:.2f}  div={div:.1e}",
          flush=True)
    return dict(u=u, v=v, xr_S=xr / S, S=S, H=H, L=L, Re=Re, div=div)


if __name__ == "__main__":
    print(f"BFS cache (backend: {'GPU/local' if _local else 'installed'})")
    res = {"S": 16, "Lr": 12}
    for Re in (100.0, 200.0):
        r = solve_bfs(Re)
        tag = f"{int(Re)}"
        for k in ("u", "v", "xr_S", "div"):
            res[f"{k}_{tag}"] = np.asarray(r[k])
        res["H"], res["L"] = r["H"], r["L"]
    np.savez(os.path.join(os.path.dirname(__file__), "bfs_cache.npz"), **res)
    print("wrote bfs_cache.npz")
