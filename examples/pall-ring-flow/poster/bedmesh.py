"""Per-ring meshes of the periodic bed, each clipped to the periodic cell's x/z walls (closed cut faces)."""
import os, sys, time, numpy as np
from skimage import measure
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ringmesh.py')).read().split('ni, nr, _, _')[0])          # -> b, home (verified tree)
PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pall-ring-packing", "pall_ring_pack.npz")
H_MESH = float(sys.argv[1]); CUT = len(sys.argv) > 2 and sys.argv[2] == "cut"                                         # mesh lattice spacing (D units)
z = np.load(PACK)
pos, quat, L = z["positions"].astype(float), z["quaternions"].astype(float), float(z["box"][0])
pos[:, 1] += -pos[:, 1].min() + 1.2                                 # flow-domain coordinates (PAD = 1.2)
def rotm(q):
    x, y, zq, w = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+zq*zq), 2*(x*y-zq*w), 2*(x*zq+y*w)],
                     [2*(x*y+zq*w), 1-2*(x*x+zq*zq), 2*(y*zq-x*w)],
                     [2*(x*zq-y*w), 2*(y*zq+x*w), 1-2*(x*x+y*y)]])
RB = 0.72
out = {}
t0 = time.time()
for k in range(len(pos)):
    Rm = rotm(quat[k])
    for ix in (-1, 0, 1):
        for iz in (-1, 0, 1):
            c = pos[k] + np.array([ix * L, 0, iz * L])
            if not (-RB < c[0] < L + RB and -RB < c[2] < L + RB):
                continue
            lo = np.maximum(c - RB, [-H_MESH, -1e9, -H_MESH]); hi = np.minimum(c + RB, [L + H_MESH, 1e9, L + H_MESH])
            n = np.ceil((hi - lo) / H_MESH).astype(int) + 1
            if (n < 3).any(): continue
            ax = [lo[d] + H_MESH * np.arange(n[d]) for d in range(3)]
            P = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
            phi = np.asarray(b.eval_root(home, (P - c) @ Rm))       # body coords = R^T (p - c)
            box = np.maximum.reduce([-P[:, 0], P[:, 0] - L, -P[:, 2], P[:, 2] - L])
            if CUT:                                                 # remove the camera-facing quadrant x < L/2, z > L/2
                box = np.maximum(box, -np.maximum(P[:, 0] - L / 2, L / 2 - P[:, 2]))
            phi = np.maximum(phi, box).reshape(n)
            if phi.min() >= 0: continue
            V, F, _, _ = measure.marching_cubes(phi, level=0.0, spacing=(H_MESH,) * 3)
            out["v_%d_%d_%d" % (k, ix, iz)] = (V + lo).astype(np.float32)
            out["f_%d_%d_%d" % (k, ix, iz)] = F.astype(np.int32)
    print("ring %d  pieces %d  %.0fs" % (k, len(out) // 2, time.time() - t0), flush=True)
np.savez_compressed("bed_mesh_cut.npz" if CUT else "bed_mesh.npz", L=L, **out)
