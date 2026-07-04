"""Helpers for the pore-mesh-voronoi example.

Everything runs through the published `peclet` package: `peclet.dem` for the packing and
`peclet.voro` for the SDF-walled interstitial Voronoi meshing (`optimize_pore_mesh`,
`sdf_voronoi_cells`). These helpers add the numpy plumbing (union-SDF seeding, graded target,
z-slice of the returned polyhedra) so the figures render in a plain numpy/matplotlib environment —
no VTK needed.
"""
from __future__ import annotations
import math
import numpy as np


def _dem():
    try:
        from peclet import dem
    except ImportError:
        import dem
    return dem


def pack_spheres(n=180, phi_ref=0.63, radius=0.5, seed=3):
    """Random close packing of `n` spheres in a periodic box, via peclet.dem (Lubachevsky–Stillinger
    growth). Returns (centres (n,3) in [0,L), radii (n,), L)."""
    dem = _dem()
    volp = (4 / 3) * math.pi * radius ** 3
    side = (n * volp / phi_ref) ** (1 / 3)
    half, dt = side / 2, 0.002
    rng = np.random.default_rng(seed)
    s = dem.Simulation(n)
    s.initialize(shape_type=1, radius=radius)
    s.set_domain((-half, -half, -half), (half, half, half))
    s.enable_periodicity(True, True, True); s.set_gravity(0, 0, 0)
    s.set_material_params(1.0, 1.0, 0.0); s.set_solver_iterations(60, 60)
    pos = rng.uniform(-half, half, (n, 4)).astype(np.float32); pos[:, 3] = 1.0
    s.set_positions(pos)
    s.set_velocities(rng.normal(0, 1, (n, 3)).astype(np.float32))
    s.set_scales(np.full(n, 1.0, np.float32))
    gr = 0.5
    s.set_growth_params(gr, 0.05); s.set_thermostat(1.0, dt)

    def ofrac():
        return float(s.compute_overlaps()) / max(2 * radius * float(s.get_scales().ravel().mean()), 1e-9)

    cool = min(int(5.0 / dt), int(7.0 / dt))
    for step in range(int(7.0 / dt)):
        if step == cool:
            s.set_material_params(0.5, 1.0, 0.0); s.set_thermostat(0.0, 1e4 * dt)
        s.step(dt); mo = ofrac()
        if mo > 5e-3:
            it = 0
            while True:
                s.step(0.0); it += 1; mn = ofrac()
                if mn >= 0.95 * mo and it > 6:
                    break
                mo = mn
            if mo > 5e-3:
                s.set_growth_params(gr * 0.85, float(s.get_growth_factor()) * math.exp(-gr * dt))
                gr *= 0.85
        else:
            gr = min(gr * 1.02, 0.5); s.set_growth_params(gr, float(s.get_growth_factor()))
    s.set_material_params(0.0, 0.0, 0.0); s.set_thermostat(0.0, 10 * dt)
    for _ in range(1200):
        s.step(dt)
    r = radius * s.get_scales().ravel() * float(s.get_growth_factor())
    c = (s.get_positions()[:, :3].astype(float) + half) % side
    return np.ascontiguousarray(c), np.ascontiguousarray(r.astype(float)), float(side)


def union_sdf(pts, centres, radii, L):
    """min_i(|x−c_i|_minimage − r_i): <0 inside a ball, >0 in the fluid (periodic box L)."""
    d = pts[:, None, :] - centres[None, :, :]
    d -= L * np.round(d / L)
    return (np.linalg.norm(d, axis=2) - radii[None, :]).min(axis=1)


def vref_graded(phi, s_lo=0.06, s_hi=0.35):
    """Graded reference cell volume V_ref = clamp(sdf, s_lo, s_hi)³ — small at the walls, capped in bulk."""
    return np.clip(phi, s_lo, s_hi) ** 3


def seed_interstitial(centres, radii, L, n, margin=0.02, graded=False, seed=1, batch=20000):
    """Reject-sample `n` seeds in the fluid (sdf>margin). If graded, weight acceptance by 1/V_ref so
    the density is ∝ 1/V_ref (dense at the walls). Returns (n,3) float64."""
    rng = np.random.default_rng(seed)
    vref_min = vref_graded(np.array([s_lo := 0.06]))[0]
    keep = []
    while sum(len(k) for k in keep) < n:
        p = rng.uniform(0, L, (batch, 3))
        phi = union_sdf(p, centres, radii, L)
        m = phi > margin
        p, phi = p[m], phi[m]
        if graded:
            acc = vref_min / vref_graded(phi)
            p = p[rng.uniform(0, 1, len(p)) < acc]
        keep.append(p)
    return np.ascontiguousarray(np.vstack(keep)[:n], dtype=np.float64)


def seed_wall_layer(centres, radii, L, per_sphere=100, eps=0.03, seed=7):
    """Inflation-layer seeds: `per_sphere` points on each sphere surface pushed out by `eps` into the
    fluid, kept only where they are actually in the fluid (not buried in a neighbouring sphere). These
    give the near-wall cells that let the SDF-clipped Voronoi cells hug the curved walls."""
    rng = np.random.default_rng(seed)
    pts = []
    for c, r in zip(centres, radii):
        u = rng.normal(size=(per_sphere, 3))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        q = (c + u * (r + eps)) % L
        pts.append(q[union_sdf(q, centres, radii, L) > 0.4 * eps])
    return np.vstack(pts)


def seed_pore_space(centres, radii, L, n_bulk, graded=False, wall_per=100, wall_eps=0.03, seed=1):
    """Interstitial seeds = a bulk cloud (uniform, or density ∝ 1/V_ref if graded) PLUS an inflation
    layer hugging every sphere, so the thin near-wall fluid is meshed and the cross-section fills up to
    the walls (a uniform bulk alone under-samples the near-wall band and the cells recede from the
    curved surface). Returns (N,3) float64."""
    bulk = seed_interstitial(centres, radii, L, n_bulk, margin=wall_eps, graded=graded, seed=seed)
    wall = seed_wall_layer(centres, radii, L, wall_per, wall_eps, seed=seed + 100)
    return np.ascontiguousarray(np.vstack([bulk, wall]))


def tile_periodic(polys, vals, L):
    """Replicate each slice polygon by ±L in x and y and keep the images that intersect the [0,L]²
    window, so cells whose seed sits near a box face — and which therefore straddle the periodic
    boundary — tile both sides instead of leaving a gap. Use at the center plane to avoid z-wrap."""
    op, ov = [], []
    for poly, v in zip(polys, vals):
        for sx in (-L, 0, L):
            for sy in (-L, 0, L):
                q = poly + (sx, sy)
                if q[:, 0].max() > 0 and q[:, 0].min() < L and q[:, 1].max() > 0 and q[:, 1].min() < L:
                    op.append(q); ov.append(v)
    return op, np.asarray(ov)


def slice_cells(cells, z0, values=None):
    """z=z0 cross-section of the polyhedra returned by peclet.voro.sdf_voronoi_cells (points + per-cell
    face lists): intersect each cell's face edges with the plane, order the crossings into a convex
    polygon. Returns (list of (k,2) polygons, values). `values` defaults to cell volume."""
    P = np.asarray(cells["points"]); faces = np.asarray(cells["faces"]); foff = np.asarray(cells["face_offsets"])
    vals = np.asarray(cells["volume"] if values is None else values)
    polys, out, prev = [], [], 0
    for ci in range(len(foff) - 1):
        blk = faces[prev:foff[ci + 1]]; prev = foff[ci + 1]
        i, nF, segs = 1, int(blk[0]), []
        for _ in range(nF):
            npf = int(blk[i]); i += 1
            Q = P[blk[i:i + npf]]; i += npf
            for k in range(npf):
                a, b = Q[k], Q[(k + 1) % npf]
                da, db = a[2] - z0, b[2] - z0
                if (da > 0) != (db > 0):
                    t = da / (da - db); segs.append(a[:2] + t * (b[:2] - a[:2]))
        if len(segs) < 3:
            continue
        pts = np.array(segs); c = pts.mean(0)
        pts = pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]
        polys.append(pts); out.append(vals[ci])
    return polys, np.asarray(out)
