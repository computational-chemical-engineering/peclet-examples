"""Run the page's own trickle-flow case for longer, and write only the movie.

The published run stops at t = 420 s.  Its own budget says why that is not enough for a
*film*: liquid injected 26208.8, liquid that left the domain 6.2e-24 — the wetting front
never reached the outlet, so the movie ends with the bed still filling.  (The comment in
the page claiming a ~300 s breakthrough was never true of the run beside it.)

This script re-uses the page's cells verbatim — bootstrap, packing, sdf, physics, driver —
so there is one definition of the case, and only overrides how far it is carried.  The
page and its published numbers are left exactly as they are.

    PECLET_LOCAL_BUILD=<suite>/flow/build_l3_cuda_final:<suite>/dem/build_l4_cuda:\
                       <suite>/core/python/build_geom:<suite>/coupling/python \
    OMP_NUM_THREADS=8 OMP_PROC_BIND=false \
    python render_long_movie.py [tend] [out.mp4]

The flow build matters: this case calls `set_contact_angle`, which the SDF-showcase-era
tree `build_l3_cuda` predates.  Against that build the run dies with an AttributeError
that a Kokkos teardown backtrace then buries.
"""
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
QMD = HERE / "index.qmd"
STOP_AT = "run-base"          # everything before the page's own run is setup we want


def cells_upto(qmd: Path, stop: str) -> list[tuple[str, str]]:
    """The page's python cells in document order, up to but excluding `stop`.

    Unlabelled cells count: a notebook shares one namespace, so skipping a cell that only
    does `import time` breaks a later one.
    """
    out = []
    for block in re.findall(r"^```\{python\}\n(.*?)^```", qmd.read_text(), re.S | re.M):
        m = re.search(r"^#\|\s*label:\s*(\S+)", block, re.M)
        label = m.group(1) if m else "(unlabelled)"
        if label == stop:
            return out
        out.append((label, block))
    sys.exit(f"cell {stop!r} not found in {qmd}")


def main() -> int:
    tend = float(sys.argv[1]) if len(sys.argv) > 1 else 1600.0
    out = sys.argv[2] if len(sys.argv) > 2 else str(HERE / "trickle-flow-packing.mp4")
    # optional grid override: the page's own half-resolution variant is 8x cheaper and
    # reaches physical times the production grid cannot in a sitting
    grid = {}
    if len(sys.argv) > 4:
        grid = {"nx": int(sys.argv[3]), "nz": int(sys.argv[4])}

    ns: dict = {"__name__": "__main__"}
    os.chdir(HERE)                       # the cells write and read beside the page
    for name, code in cells_upto(QMD, STOP_AT):
        print(f"--- cell {name}", flush=True)
        exec(compile(code, f"<{name}>", "exec"), ns)

    # Steps scale with physical time.  Measured: 60000 steps carried the production grid to
    # t = 1203 s, i.e. ~50 steps per simulated second; 60 leaves headroom as dt falls.
    max_steps = int(60 * tend)
    print(f"\n=== running to t = {tend:g} s (cap {max_steps} steps)"
          + (f" on {grid['nx']}x{grid['nx']}x{grid['nz']}" if grid else "") + " ===", flush=True)
    t0 = time.time()
    run = ns["trickle"](tend=tend, max_steps=max_steps, **grid)
    print(f"{run['steps']} steps to t = {run['t']:.0f} s in {(time.time() - t0) / 60:.0f} min",
          flush=True)
    # Save FIRST.  A three-hour run was once lost to a ZeroDivisionError in a diagnostic
    # print that ran before this line; nothing derived from the run may precede it.
    np.savez_compressed(HERE / f"trickle_long_{run['nx']}x{run['nz']}.npz",
                        frames=np.array([r["frame"] for r in run["hist"]], dtype=np.float32),
                        t=np.array([r["t"] for r in run["hist"]], dtype=np.float64),
                        outflow=np.array([r["outflow"] for r in run["hist"]]),
                        inflow=np.array([r["inflow"] for r in run["hist"]]),
                        pos=run["P"]["pos"], R=run["P"]["R"],
                        nx=run["nx"], nz=run["nz"], tend=tend,
                        total_out=run["outflow"], total_in=run["inflow"], steps=run["steps"])
    print(f"saved trickle_long_{run['nx']}x{run['nz']}.npz "
          f"({len(run['hist'])} frames)", flush=True)

    broke = breakthrough(run)
    cmax = max(float(np.max(r["frame"])) for r in run["hist"])
    print(f"  liquid injected {run['inflow']:.6g}, left {run['outflow']:.6g};  "
          f"max colour anywhere {cmax:.3f}", flush=True)
    print("  breakthrough: " + (f"t = {run['hist'][broke]['t']:.0f} s"
                                if broke is not None else "NONE — still filling at the end"),
          flush=True)
    if run["inflow"]:
        print(f"  budget defect {run['drift'] / run['inflow']:.2e} relative", flush=True)
    else:
        print("  !! NO LIQUID WAS INJECTED — the inlet did nothing; the film would be empty",
              flush=True)
    print(f"  max|div(open u)| {run['div_max']:.2e}", flush=True)
    render(ns, run, out, broke)
    return 0


def breakthrough(run, zlow: int = 3) -> int | None:
    """First history index at which liquid has reached the outlet.

    Read off the colour field, not the boundary tally: `vof_bc_volumes_total()` and
    `max_open_divergence_projected()` both return garbage in the build this runs against
    (zero injected volume, a divergence of 1e77) while the colour field is perfectly
    well behaved — bounded in [0, 1] and accumulating smoothly.  The frames are the
    trustworthy witness, and they are what the film is made of anyway.
    """
    for i, r in enumerate(run["hist"]):
        if (r["frame"][:, :zlow] > 0.5).any():
            return i
    return None


def render(ns, run, out: str, broke: int | None) -> None:
    """The page's `movie` cell, over this run's history."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import animation

    frames = [r["frame"] for r in run["hist"]]
    times = [r["t"] for r in run["hist"]]
    nx, nz = run["nx"], run["nz"]
    # the same mid-plane slice the page's fig-panels cell builds
    sdf_mid = ns["bed_sdf"](nx, nz, run["P"]["pos"], run["P"]["R"])[:, nx // 2, :]
    x = np.arange(nx) + 0.5
    z = np.arange(nz) + 0.5

    figm, axm = plt.subplots(figsize=(3.2, 6.0), dpi=110)

    def draw(k):
        axm.clear()
        axm.contourf(x, z, (sdf_mid < 0).T.astype(float), levels=[0.5, 1.5], colors=["0.72"])
        axm.contourf(x, z, np.where((sdf_mid > 0) & (frames[k] > 0.02), frames[k], np.nan).T,
                     levels=np.linspace(0, 1, 11), cmap="Blues", vmin=0, vmax=1)
        axm.contourf(x, z, (sdf_mid < 0).T.astype(float), levels=[0.5, 1.5], colors=["0.72"])
        axm.set_title(f"t = {times[k]:.0f} s")
        axm.set(xlim=(0, nx), ylim=(0, nz), aspect="equal",
                xlabel="x  [cells]", ylabel="z  [cells]")
        axm.grid(False)

    # Stop a little after the liquid first leaves the bed: the plateau that follows adds
    # running time and shows nothing new.
    last = len(frames) if broke is None else min(len(frames), int(broke * 1.25) + 10)
    every = max(1, last // 400)                 # keep the film ~20 s regardless of run length
    anim = animation.FuncAnimation(figm, draw, frames=range(0, last, every), blit=False)
    anim.save(out, fps=20, dpi=110)
    plt.close(figm)
    print(f"wrote {out} ({len(range(0, last, every))} frames of {len(frames)}, "
          f"to t = {times[last - 1]:.0f} s)", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
