"""Plumbing for the Voronoi flow-solver examples (peclet.voro.FlowSolver, track C of the Voronoi
methods plan): seed lattices, the Taylor–Green field, the SDF scene encodings of slabs and spheres,
and the steady-state march with a tight stop."""
import numpy as np


def jittered_lattice(n, L=1.0, jitter=0.2, seed=0):
    """n³ seeds on a cubic lattice of spacing L/n, jittered by ±jitter·h (a real unstructured
    Voronoi mesh — the unjittered lattice is degenerate: 8 cells meet at every vertex)."""
    rng = np.random.default_rng(seed)
    h = L / n
    g = (np.arange(n) + 0.5) * h
    X, Y, Z = np.meshgrid(g, g, g, indexing="ij")
    pos = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    pos = (pos + rng.uniform(-jitter * h, jitter * h, pos.shape)) % L
    return np.ascontiguousarray(pos)


def taylor_green(pos, t=0.0, nu=0.01, L=1.0):
    """The 2-D Taylor–Green vortex (z-independent, an exact 3-D Navier–Stokes solution):
    u = sin kx cos ky e^{-2νk²t}, v = -cos kx sin ky e^{-2νk²t}, k = 2π/L."""
    k = 2 * np.pi / L
    e = np.exp(-2 * nu * k * k * t)
    U = np.zeros_like(pos)
    U[:, 0] = np.sin(k * pos[:, 0]) * np.cos(k * pos[:, 1]) * e
    U[:, 1] = -np.cos(k * pos[:, 0]) * np.sin(k * pos[:, 1]) * e
    return U


def _node(kind, params, translation, a=-1, b=-1):
    row = np.zeros(16)
    row[: len(params)] = params
    row[8:11] = translation
    row[11:15] = (0.0, 0.0, 0.0, 1.0)
    row[15] = 1.0
    return [kind, a, b], row


def slab_scene(y_lo, y_hi, L=1.0):
    """Two solid boxes filling y < y_lo and y > y_hi (periodic box L): the fluid is the slab
    between them. Flat node encoding for Tessellation.set_geometry."""
    kBox, kUnion = 3, 32
    ints, reals = [], []
    for (i, r) in (_node(kBox, [L, 0.5 * y_lo, L], [0.5 * L, 0.5 * y_lo, 0.5 * L]),
                   _node(kBox, [L, 0.5 * (L - y_hi), L], [0.5 * L, 0.5 * (L + y_hi), 0.5 * L]),
                   _node(kUnion, [], [0, 0, 0], 0, 1)):
        ints.append(i)
        reals.append(r)
    return (np.ascontiguousarray(np.array(ints, dtype=np.int32)),
            np.ascontiguousarray(np.array(reals)), 2)


def slab_seeds(n, y_lo, y_hi, L=1.0, jitter=0.0, seed=0):
    """A cubic lattice of seeds inside the slab with the walls halfway between seed rows
    (n rows across the gap)."""
    rng = np.random.default_rng(seed)
    h = (y_hi - y_lo) / n
    nx = int(round(L / h))
    gx = (np.arange(nx) + 0.5) * h
    gy = y_lo + (np.arange(n) + 0.5) * h
    X, Y, Z = np.meshgrid(gx, gy, gx, indexing="ij")
    pos = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    if jitter:
        pos = pos + rng.uniform(-jitter * h, jitter * h, pos.shape)
    return np.ascontiguousarray(pos % L), h


def sphere_seeds(n, R, L=1.0, jitter=0.15, wall_margin=0.4, seed=0):
    """Jittered lattice seeds (spacing L/n) outside a sphere of radius R at the box centre; seeds
    closer than wall_margin·h to the surface are dropped (their cells would be slivers)."""
    rng = np.random.default_rng(seed)
    h = L / n
    g = (np.arange(n) + 0.5) * h
    X, Y, Z = np.meshgrid(g, g, g, indexing="ij")
    pos = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    pos = (pos + rng.uniform(-jitter * h, jitter * h, pos.shape)) % L
    d = np.linalg.norm(pos - 0.5 * L, axis=1) - R
    return np.ascontiguousarray(pos[d > wall_margin * h]), h


def march_to_steady(solver, dt, get_scalar, tol=1e-7, chunk=10, max_steps=20000):
    """Step until the monitored scalar changes by less than tol (relative) over a chunk."""
    prev, steps = None, 0
    while steps < max_steps:
        solver.step(chunk, dt)
        steps += chunk
        cur = get_scalar()
        if prev is not None and abs(cur - prev) < tol * abs(cur):
            break
        prev = cur
    return steps


def zick_homsy(phi):
    """Zick & Homsy (1982) Stokes drag factor K of the simple-cubic sphere array vs solid
    fraction (interpolated table)."""
    P = [0.000125, 0.001, 0.008, 0.027, 0.064, 0.125, 0.216, 0.343, 0.45, 0.5236]
    K = [1.096, 1.212, 1.525, 2.008, 2.810, 4.292, 7.442, 15.4, 28.1, 42.1]
    return float(np.interp(phi, P, K))
