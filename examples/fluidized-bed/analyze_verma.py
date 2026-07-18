"""Post-process verma_bed.npz exactly the way Verma et al. (2014) process theirs:
bubbles = connected eps > 0.7 regions in a horizontal plane (linear sub-grid interpolation),
equivalent diameter De = number average of sqrt(4A/pi) (their Eqs 1-2), rise velocity from the
area-weighted porosity cross-correlation between planes ~10 mm apart (their Eq 7, parabolic
peak interpolation), porosity PDF with 0.04 bins. Discards the first second (startup), as they do.

Usage: python analyze_verma.py <verma_bed.npz> [t_discard=1.0]
"""
import sys
import numpy as np
from scipy import ndimage

f = np.load(sys.argv[1])
t_discard = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
planes, kz, h_m = f["planes"], f["kz"], float(f["h_m"])
dt_frame = float(f["dt"]) * int(f["sample_every"])
inmask = f["inmask"]
i0 = int(round(t_discard / dt_frame))
P = planes[i0:]
print(f"frames: {len(planes)} total, {len(P)} after discarding t < {t_discard}s "
      f"(frame dt {dt_frame*1e3:.1f} ms)")

ZOOM = 4                      # linear sub-grid interpolation, as in their boundary treatment
mz = ndimage.zoom(inmask.astype(float), ZOOM, order=1) > 0.5
cell_area = (h_m / ZOOM) ** 2
min_area = 2 * h_m ** 2       # drop <2-cell specks ("very small voids" deleted, their step e)

def bubbles_in(plane):
    z = ndimage.zoom(plane, ZOOM, order=1)
    lab, n = ndimage.label((z > 0.7) & mz)
    if n == 0:
        return []
    areas = ndimage.sum_labels(np.ones_like(z), lab, np.arange(1, n + 1)) * cell_area
    return [np.sqrt(4 * A / np.pi) for A in areas if A >= min_area]

names = {0: "H = 5 cm", 2: "H = 10 cm"}
res = {}
for j, nm in names.items():
    allD = []
    for fr in P:
        allD += bubbles_in(fr[j])
    allD = np.array(allD)
    De = allD.mean() if len(allD) else np.nan
    res[nm] = (De, allD.std() if len(allD) else np.nan, len(allD))
    print(f"{nm}: De = {De*1e3:.1f} mm (std {allD.std()*1e3:.1f}, n = {len(allD)} detections)")

# rise velocity: cross-correlate area-weighted porosity between the plane pairs (their Eq 7)
for jlo, jhi, nm in [(0, 1, "H = 5 cm"), (2, 3, "H = 10 cm")]:
    dz = (kz[jhi] - kz[jlo]) * h_m
    a = P[:, jlo][:, inmask]
    b = P[:, jhi][:, inmask]
    a = a - a.mean(axis=0, keepdims=True)
    b = b - b.mean(axis=0, keepdims=True)
    nmax = int(round(0.08 / dt_frame))            # search shifts up to 80 ms
    R = np.array([np.mean(np.sum(a[:len(a) - n] * b[n:], axis=1)) for n in range(nmax)])
    n0 = int(np.argmax(R[1:]) + 1)
    if 1 <= n0 < nmax - 1:                        # parabolic (spline-like) peak interpolation
        num = R[n0 - 1] - R[n0 + 1]
        den = 2 * (R[n0 - 1] - 2 * R[n0] + R[n0 + 1])
        corr = num / den if den != 0 else 0.0
        n0 = n0 + max(-0.5, min(0.5, corr))       # a true local max shifts < half a frame
    vb = dz / (n0 * dt_frame)
    print(f"{nm}: bubble rise velocity = {vb:.2f} m/s (dz = {dz*1e3:.1f} mm, shift {n0:.2f} frames)")

# porosity PDF (0.04 bins), 5 & 10 cm planes
bins = np.arange(0.30, 1.02, 0.04)
for j, nm in names.items():
    hist, _ = np.histogram(P[:, j][:, inmask].ravel(), bins=bins, density=True)
    pk = bins[:-1][np.argmax(hist)] + 0.02
    hi = hist[bins[:-1] > 0.74]
    pkb = bins[:-1][bins[:-1] > 0.74][np.argmax(hi)] + 0.02 if hi.max() > 0 else np.nan
    print(f"{nm}: porosity PDF emulsion peak ~ {pk:.2f}, bubble-phase peak ~ {pkb:.2f}")

dPs, W_A = f["dPs"], float(f["W_over_A"])
i0d = int(round(t_discard / (float(f["dt"]) * int(f.get("diag_every", f["sample_every"])))))
print(f"dP/(W/A) over the window: {dPs[i0d:].mean()/W_A:.2f}  (W/A = {W_A:.0f} Pa)")
print(f"bed top (p98): {np.mean(f['tops'][i0d:])*100:.1f} cm (H0 = {float(f['H0'])*100:.1f} cm)")
