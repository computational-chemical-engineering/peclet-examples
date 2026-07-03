"""Helpers for the pore-mesh-voronoi example.

The volume-controlled *SDF-walled* Voronoi mesh optimiser is experimental and not yet in the released
`peclet` Python API, so this example drives a small C++ tool from a local `suite` checkout
(`pore_mesh_stages`, in `voro/examples/packed_bed_voronoi`). These helpers build+run it and read its
VTUs without needing VTK — so the figures render in a plain numpy/matplotlib environment.

Point `PECLET_SUITE` at the suite checkout (default: ~/Codes/suite).
"""
from __future__ import annotations
import math
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

SUITE = Path(os.environ.get("PECLET_SUITE", str(Path.home() / "Codes" / "suite")))
_EXDIR = SUITE / "voro" / "examples" / "packed_bed_voronoi"


def pack_spheres(n=180, phi_ref=0.63, radius=0.5, seed=3):
    """Random close packing of `n` spheres in a periodic box, via peclet.dem (Lubachevsky–Stillinger
    growth). Returns (centres (n,3) in [0,L), radii (n,), L). Needs `dem` importable."""
    try:
        from peclet import dem  # PyPI package
    except ImportError:
        import dem  # local suite build (PECLET_LOCAL_BUILD)
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
    c = (s.get_positions()[:, :3].astype(float) + half) % side  # shift into [0, L)
    return c, r.astype(float), float(side)


def write_packing(path, centres, radii, L):
    with open(path, "w") as f:
        f.write(f"{len(centres)} {L:.10g}\n")
        for c, r in zip(centres, radii):
            f.write(f"{c[0]:.10g} {c[1]:.10g} {c[2]:.10g} {r:.10g}\n")


def build_tool():
    """cmake-build the pore_mesh_stages tool against the OpenMP Kokkos prefix; return its path."""
    exe = _EXDIR / "build" / "pore_mesh_stages"
    prefix = SUITE / "extern" / "install" / "host-openmp"
    subprocess.run(["cmake", "-B", "build", f"-DCMAKE_PREFIX_PATH={prefix}",
                    "-DCMAKE_BUILD_TYPE=Release"], cwd=_EXDIR, check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["cmake", "--build", "build", "--target", "pore_mesh_stages", "-j"],
                   cwd=_EXDIR, check=True, stdout=subprocess.DEVNULL)
    return exe


def run_stages(packing_txt, outdir, n_seeds=4000, threads=8):
    """Run the 4-stage tool → outdir/stage{1..4}_*.vtu + spheres.txt."""
    exe = build_tool()
    os.makedirs(outdir, exist_ok=True)
    env = {**os.environ, "OMP_NUM_THREADS": str(threads), "OMP_PROC_BIND": "false"}
    subprocess.run([str(exe), str(packing_txt), str(outdir), str(n_seeds)], check=True, env=env)


def read_spheres(path):
    with open(path) as f:
        M, L = f.readline().split()
        c = np.array([[float(x) for x in f.readline().split()] for _ in range(int(M))])
    return c[:, :3], c[:, 3], float(L)


def slice_vtu(path, z0, array="volume"):
    """VTK-free z=z0 cross-section of a VTK_POLYHEDRON VTU: intersect each cell's face edges with the
    plane and order the crossings into a convex polygon. Returns (list of (k,2) polygons, values,
    wall-flags)."""
    piece = ET.parse(path).find(".//Piece")
    P = np.array(piece.find("Points/DataArray").text.split(), float).reshape(-1, 3)
    cells = piece.find("Cells")

    def carr(name):
        return np.array(cells.find(f"DataArray[@Name='{name}']").text.split(), np.int64)

    def darr(name):
        return np.array(piece.find(f"CellData/DataArray[@Name='{name}']").text.split(), float)

    faces, foff = carr("faces"), carr("faceoffsets")
    val, bnd = darr(array), darr("boundary")
    polys, vals, wall, prev = [], [], [], 0
    for ci, end in enumerate(foff):
        blk = faces[prev:end]; prev = end
        i, nF = 1, int(blk[0])
        segs = []
        for _ in range(nF):
            npf = int(blk[i]); i += 1
            Q = P[blk[i:i + npf]]; i += npf
            for k in range(npf):
                a, b = Q[k], Q[(k + 1) % npf]
                da, db = a[2] - z0, b[2] - z0
                if (da > 0) != (db > 0):
                    t = da / (da - db)
                    segs.append(a[:2] + t * (b[:2] - a[:2]))
        if len(segs) < 3:
            continue
        pts = np.array(segs)
        c = pts.mean(0)
        pts = pts[np.argsort(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))]
        polys.append(pts); vals.append(val[ci]); wall.append(bnd[ci])
    return polys, np.asarray(vals), np.asarray(wall)
