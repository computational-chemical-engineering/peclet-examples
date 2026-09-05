#!/usr/bin/env python3
"""Render the tennis-racket flip as an mp4, from the page's own simulation.

The page already animates this, but as `to_jshtml` - which embeds every frame as base64 in
the HTML.  That is exactly the weight the gallery's own rule sends to YouTube instead, so
this writes a video file and the page can embed it.

Re-uses the page's cells verbatim up to the animation, so the movie shows the same run the
page's numbers come from rather than a re-implementation.

    OMP_NUM_THREADS=1 PECLET_LOCAL_BUILD=<dem>:<core geom> \
    python render_racket_movie.py [out.mp4] [--frames 240] [--fps 24]
"""
import argparse
import os
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
QMD = HERE / "index.qmd"
STOP_AT = "fig-movie"


def cells_upto(qmd: Path, stop: str):
    out = []
    for block in re.findall(r"^```\{python\}\n(.*?)^```", qmd.read_text(), re.S | re.M):
        m = re.search(r"^#\|\s*label:\s*(\S+)", block, re.M)
        label = m.group(1) if m else "(unlabelled)"
        if label == stop:
            return out
        out.append((label, block))
    sys.exit(f"cell {stop!r} not found in {qmd}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", default=str(HERE / "tennis_racket.mp4"))
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()

    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OMP_PROC_BIND", "false")
    os.chdir(HERE)
    ns = {"__name__": "__main__"}
    for name, code in cells_upto(QMD, STOP_AT):
        print(f"--- cell {name}", flush=True)
        exec(compile(code, f"<{name}>", "exec"), ns)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import animation
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from skimage import measure

    b, sp, half, order = ns["b"], ns["sp"], ns["half"], ns["order"]
    t_sim, q_sim, quat_matrix = ns["t_sim"], ns["q_sim"], ns["quat_matrix"]

    nb = 72                                        # a little finer than the page's 64
    spc = 2 * half / (nb - 1)
    g = np.asarray(b.bake(sp.home_root, origin=[-half] * 3, spacing=[spc] * 3,
                          dims=[nb, nb, nb]))
    vm, fm, _, _ = measure.marching_cubes(
        np.ascontiguousarray(g.reshape(nb, nb, nb, order="F")), level=0.0,
        spacing=(spc, spc, spc))
    vm = vm - half
    # Colour by body-frame height over the body's ACTUAL range: the page's fixed +-0.6
    # leaves almost every face in the middle of coolwarm, which is white, and a white body
    # on a white ground has no readable orientation at all.
    hgt = vm[fm][:, :, order[2]].mean(axis=1)
    fc = plt.cm.coolwarm(plt.Normalize(hgt.min(), hgt.max())(hgt))

    idx = np.linspace(0, len(t_sim) - 1, args.frames).astype(int)
    fig = plt.figure(figsize=(7.2, 7.2), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("white")

    # The body tumbles, so the frame has to hold its bounding SPHERE - but only that, or
    # it sits tiny in the middle of an empty plot, which is how the first render came out.
    lim = float(np.linalg.norm(vm, axis=1).max()) * 1.04

    def frame(i):
        ax.clear()
        R = quat_matrix(q_sim[idx[i]])
        ax.add_collection3d(Poly3DCollection((vm @ R.T)[fm], facecolors=fc,
                                             edgecolor=(0.25, 0.28, 0.32, 0.25), linewidths=0.15))
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
        ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()
        ax.view_init(elev=18, azim=-60)
        ax.set_title("torque-free rotation about the intermediate axis\n"
                     "t = %5.2f s" % t_sim[idx[i]], fontsize=13)
        return []

    anim = animation.FuncAnimation(fig, frame, frames=args.frames, blit=False)
    anim.save(args.out, fps=args.fps, dpi=args.dpi,
              extra_args=["-pix_fmt", "yuv420p", "-vcodec", "libx264", "-crf", "20"])
    plt.close(fig)
    size = Path(args.out).stat().st_size / 1e6
    print(f"wrote {args.out}  {args.frames} frames at {args.fps} fps "
          f"({args.frames/args.fps:.1f} s, {size:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
