#!/usr/bin/env python3
"""Bubble interfaces (and a liquid-velocity panel) from a run_peclet.py checkpoint, for render.py.

    python bubbles_mesh.py <ckpt.npz> <out_mesh.npz>       (suite venv: numpy, scipy, scikit-image)

The checkpoint holds every marker's own colour field C_k on its moving box ("box<i>" = lo, hi in
cell indices, hi exclusive, "col<i>" = C_k), in UNWRAPPED cell coordinates: x (vertical) and z
(spanwise) are periodic and a box that has crossed a periodic face keeps counting past it. So each
bubble is meshed whole from its own field, and then shifted by whole periods so that its centroid
lies in the column: a bubble crossing a periodic face is drawn whole on one side (it may stick out
of the box by up to a radius), never cut in two.

Interface: the C_k = 1/2 isosurface by marching cubes on the box padded with one ring of C = 0
(closes a bubble touching a wall at the wall), then Taubin smoothing (lambda 0.5, mu -0.53,
30 passes) to remove the marching-cubes facets of a sharp VoF field. The raw marching-cubes surface
of a sharp field encloses ~1.4 % less than the marker volume sum(C_k) h^3; after the smoothing the
two agree to a few 0.1 % (printed: the max relative difference over the bubbles).

Liquid panel: the vertical liquid velocity at cell centres, averaged over the depth (z) with the
liquid fraction 1 - C as weight, C = max_k C_k the union colour; positive = DOWN (the page's sign).
Everything in D = 1 units, in the solver frame (x down, y wall-normal, z spanwise); render.py maps
it to Blender's z-up frame.
"""
import os
import sys

import numpy as np
from skimage.measure import marching_cubes

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import case  # noqa: E402


def taubin(V, F, n=30, lam=0.5, mu=-0.53):
    """Umbrella-operator Taubin smoothing on a closed triangle mesh."""
    nv = len(V)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    E = np.unique(np.sort(np.concatenate([E, E[:, ::-1]]), axis=1), axis=0)
    i, j = np.concatenate([E[:, 0], E[:, 1]]), np.concatenate([E[:, 1], E[:, 0]])
    deg = np.bincount(i, minlength=nv).astype(float)[:, None]
    for _ in range(n):
        for f in (lam, mu):
            S = np.zeros_like(V)
            np.add.at(S, i, V[j])
            V = V + f * (S / np.maximum(deg, 1) - V)
    return V


def mesh_volume(V, F):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0


def main():
    ck, out = sys.argv[1], sys.argv[2]
    z = np.load(ck)
    S, h = case.CELLS_PER_D, case.H
    N = np.array([case.NX, case.NY, case.NZ])
    L = N * h
    nb = int(z["nblocks"])
    Cu = np.zeros(tuple(N))
    meshes, cents, vols = {}, [], []
    for k in range(nb):
        lo = np.asarray(z[f"box{k}"])[:3]
        c = np.asarray(z[f"col{k}"], float)
        # union colour on the periodic grid (y is never wrapped: walls)
        ix = (lo[0] + np.arange(c.shape[0])) % N[0]
        iy = lo[1] + np.arange(c.shape[1])
        iz = (lo[2] + np.arange(c.shape[2])) % N[2]
        sub = Cu[np.ix_(ix, iy, iz)]
        Cu[np.ix_(ix, iy, iz)] = np.maximum(sub, c)
        cp = np.pad(c, 1)
        V, F, _, _ = marching_cubes(cp, 0.5)
        V = (V - 1 + lo + 0.5) * h                      # padded index -> cell-centre position
        V = taubin(V, F)
        vol_c = c.sum() * h ** 3
        vol_m = mesh_volume(V, F)
        if vol_m < 0:                                   # outward normals (right-handed winding)
            F, vol_m = F[:, ::-1].copy(), -vol_m
        w = c / c.sum()
        cen = np.array([(w.sum(axis=(1, 2)) * (lo[0] + np.arange(c.shape[0]) + 0.5)).sum(),
                        (w.sum(axis=(0, 2)) * (lo[1] + np.arange(c.shape[1]) + 0.5)).sum(),
                        (w.sum(axis=(0, 1)) * (lo[2] + np.arange(c.shape[2]) + 0.5)).sum()]) * h
        shift = np.array([np.floor(cen[0] / L[0]) * L[0], 0.0, np.floor(cen[2] / L[2]) * L[2]])
        V, cen = V - shift, cen - shift
        meshes[f"V{k}"], meshes[f"F{k}"] = V.astype(np.float32), F.astype(np.int32)
        cents.append(cen)
        vols.append((vol_c, vol_m))
    vols = np.array(vols)
    rel = np.abs(vols[:, 1] / vols[:, 0] - 1)
    u = z["u"] / S                                       # x-face velocity, physical; + = down
    uc = 0.5 * (u + np.roll(u, -1, axis=0))
    wl = 1.0 - np.clip(Cu, 0, 1)
    ul_xy = (wl * uc).sum(axis=2) / np.maximum(wl.sum(axis=2), 1e-30)
    np.savez_compressed(out, nblocks=nb, centroid=np.array(cents), vol_marker=vols[:, 0],
                        vol_mesh=vols[:, 1], L=L, h=h, t=float(z["t"]), step=int(z["step"]),
                        ul_xy=ul_xy.astype(np.float32), **meshes)
    print(f"wrote {out}: t {float(z['t']):.2f}, {nb} bubbles, mesh/marker volume max rel diff "
          f"{rel.max():.2e}, liquid u range {ul_xy.min():+.3f} .. {ul_xy.max():+.3f}")


if __name__ == "__main__":
    main()
