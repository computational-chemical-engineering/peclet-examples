"""Equivalent bubble diameter vs height, De(H), from the saved 3-D eps frames — the direct
analogue of Verma et al. (2014) Figure 14. Same detection as analyze_verma.py (eps > 0.7,
linear sub-grid interpolation, number-averaged sqrt(4A/pi)), applied at every grid height.
Writes verma_profile.npz. Usage: python compute_verma_profile.py <frames_dir> <out.npz>
"""
import glob, sys
import numpy as np
from scipy import ndimage

frames_dir, out = sys.argv[1], sys.argv[2]
files = sorted(glob.glob(frames_dir + "/f*.npz"))
h_m = 0.10 / 32
i0 = int(round(1.0 / 0.010))                  # discard t < 1 s (frames are 10 ms)
files = files[i0:]
print(f"{len(files)} frames after discard")

e0 = np.load(files[0])["eps"].astype(np.float32)
NX, NY, NZ = e0.shape
xi, yi = np.meshgrid(np.arange(NX) + .5, np.arange(NY) + .5, indexing="ij")
inmask = np.hypot(xi - 17.0, yi - 17.0) < 16.0 - 0.5
ZOOM = 4
mz = ndimage.zoom(inmask.astype(float), ZOOM, order=1) > 0.5
cell_area = (h_m / ZOOM) ** 2
min_area = 2 * h_m ** 2

kzs = np.arange(4, 68)                        # 1.4 cm .. 21 cm
sums = np.zeros(len(kzs)); counts = np.zeros(len(kzs), dtype=int)
for fi, fn in enumerate(files):
    eps = np.load(fn)["eps"].astype(np.float32)
    for j, kz in enumerate(kzs):
        z = ndimage.zoom(eps[:, :, kz], ZOOM, order=1)
        lab, n = ndimage.label((z > 0.7) & mz)
        if n == 0:
            continue
        areas = ndimage.sum_labels(np.ones_like(z), lab, np.arange(1, n + 1)) * cell_area
        for A in areas:
            if A >= min_area:
                sums[j] += np.sqrt(4 * A / np.pi); counts[j] += 1
    if fi % 100 == 0:
        print(f"frame {fi}/{len(files)}", flush=True)

H = (kzs + 0.5) * h_m
De = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
np.savez_compressed(out, H=H, De=De, counts=counts)
for j in range(0, len(kzs), 8):
    print(f"H = {H[j]*100:5.1f} cm  De = {De[j]*1e3:5.1f} mm  (n={counts[j]})")
print("saved", out)
