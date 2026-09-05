#!/usr/bin/env python3
"""Turn a rivulet run into a film: grains in stone, liquid as a lit isosurface.

The gallery's other trickle movie is a mid-plane contour, which is the right picture for
reading a budget off and the wrong one for seeing rivulets - a plane through a packing cuts
most of the liquid away.  This renders the gas-liquid interface in three dimensions instead,
with the grains behind it, so the films and the paths between them are what you see.

    python render_rivulets_3d.py rivulets_96x192 [--out trickle_rivulets.mp4] [--spin 25]
"""
import argparse
import json
from pathlib import Path

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--spin", type=float, default=25.0, help="degrees of camera drift")
    ap.add_argument("--size", type=int, nargs=2, default=(1080, 1350))
    ap.add_argument("--every", type=int, default=1)
    args = ap.parse_args()

    import pyvista as pv
    import imageio.v2 as imageio
    pv.OFF_SCREEN = True

    geo = np.load(args.run / "geometry.npz")
    sdf = geo["sdf"].astype(np.float32)
    nx, nz = int(geo["nx"]), int(geo["nz"])
    z0, z1 = float(geo["z0"]), float(geo["z1"])
    frames = sorted(args.run.glob("C_*.npz"))[:: args.every]
    if not frames:
        raise SystemExit(f"no frames in {args.run}")
    hist = json.loads((args.run / "history.json").read_text()) \
        if (args.run / "history.json").exists() else {"hist": []}
    times = {int(f.stem.split("_")[1]): None for f in frames}

    grid = pv.ImageData(dimensions=(nx + 1, nx + 1, nz + 1), spacing=(1, 1, 1))

    def image_of(arr):
        g = pv.ImageData(dimensions=arr.shape, spacing=(1, 1, 1), origin=(0.5, 0.5, 0.5))
        g.point_data["v"] = arr.ravel(order="F")
        return g

    grains = image_of(sdf).contour([0.0], scalars="v")
    grains = grains.clip_box([0, nx, 0, nx, z0 - 1, z1 + 1], invert=False)

    writer = imageio.get_writer(args.out or args.run.parent / "trickle_rivulets.mp4",
                                fps=args.fps, quality=9, macro_block_size=1)
    pl = pv.Plotter(off_screen=True, window_size=list(args.size), lighting="three lights")
    zmid = 0.5 * (z0 + z1)

    for n, f in enumerate(frames):
        d = np.load(f)
        C = d["C"].astype(np.float32)
        t = float(d["t"])
        pl.clear()
        pl.set_background("#0E1116")
        pl.add_mesh(grains, color="#9aa3ad", smooth_shading=True,
                    specular=0.25, specular_power=12, opacity=1.0)
        try:
            iso = image_of(C).contour([0.5], scalars="v")
            if iso.n_points:
                iso = iso.clip_box([0, nx, 0, nx, 0, z1 + 8], invert=False)
                iso["height"] = iso.points[:, 2]
                pl.add_mesh(iso, scalars="height", cmap="ocean_r", show_scalar_bar=False,
                            smooth_shading=True, specular=0.9, specular_power=40,
                            opacity=0.96)
        except Exception:
            pass
        # the column, so the eye has a frame to read the bed against
        pl.add_mesh(pv.Box([0, nx, 0, nx, z0, z1]).extract_all_edges(),
                    color="#2b3542", line_width=2)
        az = -60 + args.spin * np.sin(2 * np.pi * n / max(len(frames), 1))
        r = 2.6 * nx
        pl.camera_position = [
            (nx / 2 + r * np.cos(np.radians(az)), nx / 2 + r * np.sin(np.radians(az)), zmid + 0.35 * nz),
            (nx / 2, nx / 2, zmid), (0, 0, 1)]
        pl.add_text(f"t = {t:6.0f} s", position="upper_left", font_size=13, color="#dfe6ee")
        writer.append_data(pl.screenshot(return_img=True))
        if n % 20 == 0:
            print(f"  frame {n}/{len(frames)}  t={t:.0f}s", flush=True)
    writer.close()
    pl.close()
    out = args.out or args.run.parent / "trickle_rivulets.mp4"
    print(f"wrote {out}  {len(frames)} frames  {out.stat().st_size/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
