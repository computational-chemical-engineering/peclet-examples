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

    # MONOTONIC growth: relax overlaps at the CURRENT size (dt = 0 steps grow nothing) and only slow
    # the growth rate — never un-grow. The old shrink-on-overlap scheme was a knife-edge that, under
    # the atomically non-deterministic GPU contact solve, quenched a loose bed on some seeds; growing
    # one-directionally makes the packing land reproducibly at the box-limited phi_ref (Z ~ 6).
    cool = min(int(5.0 / dt), int(7.0 / dt))
    for step in range(int(7.0 / dt)):
        if step == cool:
            s.set_material_params(0.5, 1.0, 0.0); s.set_thermostat(0.0, 1e4 * dt)
        s.step(dt); mo = ofrac()
        gf = float(s.get_growth_factor())
        if mo > 5e-3:
            it = 0; prev = mo
            while it < 40:
                s.step(0.0); it += 1; mn = ofrac()
                if mn < 5e-3 or (it > 8 and mn > 0.98 * prev):
                    break
                prev = mn
            if ofrac() > 5e-3:
                gr = max(gr * 0.8, 0.02); s.set_growth_params(gr, gf)   # slow growth, keep size
        elif gf >= 1.0 - 1e-6:
            break
        else:
            gr = min(gr * 1.02, 0.5); s.set_growth_params(gr, gf)
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


def _fib_sphere(n):
    """`n` roughly-even points on the unit sphere (Fibonacci spiral)."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.c_[np.sin(phi) * np.cos(theta), np.sin(phi) * np.sin(theta), np.cos(phi)]


def seed_graded(centres, radii, L, s_lo=0.10, s_hi=0.35, margin=0.01, jitter=0.35, seed=1):
    """Distance-graded seeding that *realises the target cell-size field* s(φ)=clip(φ, s_lo, s_hi).

    Instead of rejection-sampling a density (which places Poisson-clustered points that don't hit a
    target size), lay down concentric shells around every sphere: a shell at distance ``d`` from the
    wall, with both its radial step to the next shell AND its in-surface point spacing equal to the
    local size ``s(d)``. A seed at distance φ from the nearest wall then gets a Voronoi cell of size
    ≈ s(φ) — genuinely small (``s_lo``) hugging the curved walls and growing to ``s_hi`` in the open
    pores: a body-fitted inflation-layer mesh straight from the seeding, no relaxation. Pass
    ``s_lo == s_hi`` for a uniform mesh. Points are jittered off the shells (blue-noise-ish) and kept
    only near their own layer distance, so each fluid point is meshed once at the right scale.
    Returns (N,3) float64. N grows like ~area/s_lo², so keep ``s_lo`` ≳ 0.08 for a packed bed."""
    rng = np.random.default_rng(seed)
    dists, d = [], 0.6 * s_lo
    while d < 3 * s_hi:
        dists.append(d)
        d += float(np.clip(d, s_lo, s_hi))
    pts = []
    for d in dists:
        h = float(np.clip(d, s_lo, s_hi))
        for c, r in zip(centres, radii):
            R = r + d
            n = max(6, int(4 * np.pi * R * R / (h * h)))
            p = _fib_sphere(n) * R + c + rng.normal(0, jitter * h, (n, 3))
            phi = union_sdf(p % L, centres, radii, L)
            pts.append((p % L)[np.abs(phi - d) < 0.75 * h])   # keep points near their own layer
    return np.ascontiguousarray(np.vstack(pts))


def section_cells(positions, centres, radii, L, z0):
    """Cross-section polygons of the SDF-clipped Voronoi mesh at the plane z=z0, via
    ``peclet.voro.sdf_voronoi_section`` — which cuts every cell directly from its dual structure
    (``ConvexCell::sectionPolygon``), so the plane tiles exactly (no fragile face-by-face slicing).
    Returns (list of (k,2) polygons, per-cell volume, per-cell seed index)."""
    from peclet import voro
    sec = voro.sdf_voronoi_section(np.ascontiguousarray(positions, dtype=np.float64),
                                   centres, radii, L, (0.0, 0.0, float(z0)), (0.0, 0.0, 1.0))
    verts = np.asarray(sec["verts"]); off = np.asarray(sec["offsets"])
    polys = [verts[off[i]:off[i + 1], :2] for i in range(len(off) - 1)]
    return polys, np.asarray(sec["volume"]), np.asarray(sec["seed"])


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
