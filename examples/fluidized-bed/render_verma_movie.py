"""Render the bubble-contour movie from the saved 3-D eps frames (Verma Fig. 6 style):
the eps = 0.7 isosurface (bubble boundaries) inside the column outline, side view.
Usage: python render_verma_movie.py <frames_dir> <out.mp4>
"""
import glob, sys
import numpy as np
import pyvista as pv
import imageio.v2 as imageio

pv.OFF_SCREEN = True
frames_dir, out = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(frames_dir + "/f*.npz"))[50:]   # from t = 0.5 s
h_mm = 100.0 / 32

cyl = pv.CylinderStructured(radius=np.linspace(15.9, 16.0, 2), height=110.0,
                            center=(17, 17, 55), direction=(0, 0, 1),
                            theta_resolution=90, z_resolution=2)
writer = imageio.get_writer(out, fps=25, quality=8)
pl = pv.Plotter(off_screen=True, window_size=(480, 1040))
for i, fn in enumerate(files):
    eps = np.load(fn)["eps"].astype(np.float32)
    grid = pv.ImageData(dimensions=eps.shape, spacing=(1, 1, 1), origin=(0.5, 0.5, 0.5))
    grid.point_data["eps"] = eps.ravel(order="F")
    pl.clear()
    try:
        iso = grid.contour([0.7], scalars="eps")
        if iso.n_points:
            pl.add_mesh(iso, color="#1d7a3e", smooth_shading=True,
                        specular=0.35, opacity=0.5)
    except Exception:
        pass
    pl.add_mesh(cyl, color="#bbbbbb", opacity=0.12)
    pl.camera_position = [(240, 17, 55), (17, 17, 55), (0, 0, 1)]
    pl.camera.parallel_projection = True
    pl.camera.parallel_scale = 60
    pl.add_text(f"t = {0.5 + i*0.010:.2f} s", font_size=10, color="black")
    pl.set_background("white")
    writer.append_data(pl.screenshot(return_img=True))
    if i % 100 == 0:
        print(f"frame {i}/{len(files)}", flush=True)
writer.close()
print("wrote", out)
