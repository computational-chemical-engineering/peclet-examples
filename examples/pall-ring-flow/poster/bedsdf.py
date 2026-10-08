"""Signed distance of the periodic bed on a lattice (spacing h/2, cell-centred), min over local per-ring bakes."""
import os, sys, time, numpy as np
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ringmesh.py')).read().split('ni, nr, _, _')[0])          # -> b, home (verified tree)
PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pall-ring-packing", "pall_ring_pack.npz")
z = np.load(PACK)
pos, quat, L = z["positions"].astype(float), z["quaternions"].astype(float), float(z["box"][0])


def rotm(q):
    x, y, zq, w = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+zq*zq), 2*(x*y-zq*w), 2*(x*zq+y*w)], [2*(x*y+zq*w), 1-2*(x*x+zq*zq), 2*(y*zq-x*w)],
                     [2*(x*zq-y*w), 2*(y*zq+x*w), 1-2*(x*x+y*y)]])


f = np.load(sys.argv[1]); h = float(f["h"]) / 2; n = 2 * np.asarray(f["cells"]); pos[:, 1] += float(f["yshift"])
out = np.full(n, 0.5, np.float32)                                  # 0.5 D cap: only the near-wall band matters
t0 = time.time(); RB = 0.75
for k in range(len(pos)):
    Rm = rotm(quat[k])
    for ix in (-1, 0, 1):
        for iz in (-1, 0, 1):
            c = pos[k] + [ix * L, 0, iz * L]
            lo = np.floor((c - RB) / h - 0.5).astype(int); hi = np.ceil((c + RB) / h - 0.5).astype(int)
            I = [np.arange(lo[d], hi[d] + 1) for d in range(3)]
            I = [a[(a >= 0) & (a < n[d])] for d, a in enumerate(I)]
            if min(len(a) for a in I) == 0:
                continue
            P = np.stack(np.meshgrid(*[(a + 0.5) * h for a in I], indexing="ij"), -1).reshape(-1, 3)
            phi = np.asarray(b.eval_root(home, (P - c) @ Rm), np.float32).reshape([len(a) for a in I])
            sub = np.ix_(*I); out[sub] = np.minimum(out[sub], phi)
    print(k, "%.0fs" % (time.time() - t0), flush=True)
print("baked %s in %.0fs, solid frac %.3f" % (out.shape, time.time() - t0, (out < 0).mean()), flush=True)
np.save(sys.argv[2], out)
