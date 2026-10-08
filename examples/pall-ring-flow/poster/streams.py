"""Streamlines of the steady bed flow: RK4 in arclength on the cell-centred velocity, periodic in x, z."""
import sys, numpy as np
from scipy.ndimage import map_coordinates
fz = np.load(sys.argv[1]); NSEED = int(sys.argv[2]); OUT = sys.argv[3]
u, v, w = fz["u"], fz["v"], fz["w"]; h = float(fz["h"]); nx, ny, nz = u.shape
# staggered MAC: u at (i+1/2, j, k) in cell index units -> average the two faces of each cell
uc = 0.5 * (u + np.roll(u, 1, 0)); vc = 0.5 * (v + np.roll(v, 1, 1)); wc = 0.5 * (w + np.roll(w, 1, 2))
U = np.stack([uc, vc, wc]); Ly = ny * h; Lx = nx * h
Umean = float(v.mean())
def vel(P):                                   # P in physical coords, cell centres at (i+1/2) h
    g = (P.T / h) - 0.5
    return np.stack([map_coordinates(U[c], g, order=1, mode="grid-wrap") for c in range(3)], 1)
rng = np.random.default_rng(int(sys.argv[4]) if len(sys.argv) > 4 else 1)
m = int(np.ceil(np.sqrt(NSEED)))
gx, gz = np.meshgrid((np.arange(m) + 0.5) / m, (np.arange(m) + 0.5) / m, indexing="ij")
S = np.stack([gx.ravel(), np.zeros(m * m), gz.ravel()], 1)
S[:, [0, 2]] += (rng.random((m * m, 2)) - 0.5) / m
S[:, 0] *= Lx; S[:, 2] *= Lx; S[:, 1] = 0.25
P = S.copy(); ds = 0.25 * h; alive = np.ones(len(P), bool)
ylag = np.zeros((len(P), 600)); paths = [[p.copy()] for p in P]; speeds = [[0.0] for _ in P]
SDF = np.load(sys.argv[5]) if len(sys.argv) > 5 else None
if SDF is not None:
    h2 = h / 2; G = [(np.roll(SDF, -1, a) - np.roll(SDF, 1, a)) / (2 * h2) for a in range(3)]
    D0 = 0.5 * h
def guard(X):
    if SDF is None: return X
    g = (X.T / h2) - 0.5
    phi = map_coordinates(SDF, g, order=1, mode="grid-wrap")
    bad = phi < D0
    if bad.any():
        gr = np.stack([map_coordinates(G[a], g[:, bad], order=1, mode="grid-wrap") for a in range(3)], 1)
        gr /= np.maximum(np.linalg.norm(gr, axis=1), 1e-12)[:, None]
        X[bad] += (D0 - phi[bad])[:, None] * gr
    return X
def dirn(P):
    V = vel(P); s = np.linalg.norm(V, axis=1); return V / np.maximum(s, 1e-30)[:, None], s
for it in range(int(4.0 * Ly / ds)):
    idx = np.nonzero(alive)[0]
    if len(idx) == 0: break
    X = P[idx]
    k1, s1 = dirn(X); k2, _ = dirn(X + 0.5 * ds * k1); k3, _ = dirn(X + 0.5 * ds * k2); k4, _ = dirn(X + ds * k3)
    Xn = guard(X + ds / 6 * (k1 + 2 * k2 + 2 * k3 + k4))
    P[idx] = Xn
    _, sn = dirn(Xn)
    for j, i in enumerate(idx):
        if it % 2 == 0: paths[i].append(Xn[j].copy()); speeds[i].append(sn[j])
    ylag[idx, it % 600] = Xn[:, 1]
    stuck = (it > 600) & (Xn[:, 1] - ylag[idx, (it + 1) % 600] < 0.03)
    stop = (Xn[:, 1] > Ly - 0.25) | (sn < 1e-7 * Umean) | stuck
    alive[idx[stop]] = False
pts = [np.asarray(p) for p in paths]; spd = [np.asarray(s) for s in speeds]; spd = [np.r_[s[1], s[1:]] for s in spd]
reached = np.array([p[-1, 1] > Ly - 0.3 for p in pts])
print("seeds %d  reached top %d  mean pts %.0f  Umean %.4f  max speed/Umean %.1f"
      % (len(pts), reached.sum(), np.mean([len(p) for p in pts]), Umean, max(s.max() for s in spd) / Umean))
off = np.cumsum([0] + [len(p) for p in pts])
np.savez_compressed(OUT, yshift=float(fz['yshift']) if 'yshift' in fz else 0.0, P=np.concatenate(pts).astype(np.float32), S=np.concatenate(spd).astype(np.float32),
                    off=off, reached=reached, Umean=Umean, L=Lx, Ly=Ly, h=h)
