"""Rebuild the Pall ring tree exactly as the packing page did, check it against the .npz, bake a fine mesh."""
import os, sys, numpy as np
from peclet import geom
from skimage import measure
PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pall-ring-packing", "pall_ring_pack.npz")
R_O, H, T = 0.5, 1.0, 0.12; NWIN, YWIN = 4, 0.24; WR, WA, WT = 0.16, 0.17, 0.13; WEB = (0.40, 0.06, 0.06)
def qy(a): return [0.0, float(np.sin(0.5 * a)), 0.0, float(np.cos(0.5 * a))]
b = geom.SceneBuilder()
tube = b.add_leaf("hollow_cylinder", [R_O, H, T])
wins = []
for row, ysign in enumerate((+1, -1)):
    for k in range(NWIN):
        phi = 2 * np.pi * k / NWIN + (np.pi / NWIN if row else 0.0)
        wins.append(b.add_leaf("box", [WR, WA, WT], translation=[R_O * np.cos(phi), ysign * YWIN, R_O * np.sin(phi)], rotation=qy(-phi)))
w = wins[0]
for x in wins[1:]: w = b.add_union(w, x)
shell = b.add_difference(tube, w)
ring = b.add_union(b.add_union(shell, b.add_leaf("box", list(WEB), translation=[0.0, +YWIN, 0.0])),
                   b.add_leaf("box", list(WEB), translation=[0.0, -YWIN, 0.0], rotation=qy(np.pi / 2)))
home = b.principal_frame(ring, lo=[-0.56] * 3, hi=[0.56] * 3, n=32, order=5, nseg=8)
ni, nr, _, _ = b.encode()
z = np.load(PACK)
print("home", home, int(z["home_root"]), "ints equal", np.array_equal(np.asarray(ni), z["node_ints"]),
      "reals maxdiff", np.abs(np.asarray(nr, float) - z["node_reals"].astype(float)).max())
N = int(sys.argv[1]); HALF = 0.62; SPC = 2 * HALF / (N - 1)
gv = np.asarray(b.bake(home, origin=[-HALF] * 3, spacing=[SPC] * 3, dims=[N] * 3))
V, F, Nrm, _ = measure.marching_cubes(np.ascontiguousarray(gv.reshape(N, N, N, order="F")), level=0.0, spacing=(SPC,) * 3)
V -= HALF
print("verts", len(V), "faces", len(F))
np.savez("ring_mesh.npz", V=V.astype(np.float32), F=F.astype(np.int32), N=Nrm.astype(np.float32))
