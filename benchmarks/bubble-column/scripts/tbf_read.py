#!/usr/bin/env python3
"""Read a TBFsolver bubble-column run and reduce every snapshot to the benchmark observables.

    python tbf_read.py <run dir> [--out tbf_timeseries.npz] [--every 1]

TBFsolver output (`src/fields/field/field.f90::writeField`, `src/time/time.f90`):

  * snapshots are the numbered folders 1, 2, ... of the run directory, each with an `info_restart`
    (line 1 the time, line 2 the bubble count). A folder is written at the FIRST step with
    t >= k * dtout, so snapshot times are k*dtout + O(dt), not exact multiples — use the time
    stored here, never the folder number, when comparing with peclet.
  * every field file is a stream: one int32 (the value count), then that many float64 in Fortran
    order (x fastest). Cell fields (c, cs, k, p, p0, psi, wx, wy, wz) are (nx, ny, nz); the
    staggered velocity components are ux (nx+1, ny, nz), uy (nx, ny+1, nz), uz (nx, ny, nz+1),
    face i sitting at x = i*dx (i = 0..nx), so ux[0] and ux[nx] are the same periodic face and
    uy[:, 0] = uy[:, ny] = 0 are the walls. Cell i (1-based) is centred at (i - 1/2) dx.
  * `c` is the GAS volume fraction, the max over the per-bubble markers (multiple-marker VoF);
    `cs` is its smoothed copy from which rho and mu are built.
  * `b<n>` holds bubble n's own marker: int32 master, int32 bn, int32 idx(6) = (is, ie, js, je,
    ks, ke) in global 1-based cell indices (they may run past 1..nx in the periodic directions),
    then float64 c0 over (is-3:ie+3, js-3:je+3, ks-3:ke+3), Fortran order. At a snapshot
    c0 equals the block's current c (`VOF.f90::cn0` runs after the advection).

Per snapshot this computes (x is vertical, gravity along +x, bubbles rise towards -x):

  gas_volume          sum(c) dV
  u_gas[3]            <c u> / <c>               (gas-phase mean velocity, per component)
  u_mix[3]            <u>                       (mixture = volume-averaged velocity)
  u_liq[3]            <(1-c) u> / <1-c>
  rise_speed          -(u_gas - u_mix)_x        drift velocity, positive when rising
  slip_speed          -(u_gas - u_liq)_x        gas-liquid slip, positive when rising
  momentum[3]         <rho u>, rho = rho_g cs + rho_l (1 - cs) as TBFsolver builds it; the
                      continuous problem has zero net body force, so any drift of <rho u>_x
                      away from 0 is what the walls and the discretisation put in
  alpha_y, u_liq_y, u_gas_y   plane (x,z) averages across the wall-normal y:
                      <c>, <(1-c) u_x>/<1-c>, <c u_x>/<c>   (u_gas_y NaN where no gas)
  bubble_pos[nb,3]    per-bubble centroid from its own marker, wrapped into the box
  bubble_vol[nb]      per-bubble volume
  bubble_vel[nb,3]    per-bubble marker-weighted mean velocity

Velocities are first interpolated to cell centres (the arithmetic mean of the two faces), which is
the same averaging TBFsolver itself uses for its CFL and its bubble statistics. If `run.log` is
present its per-step t, dt and CFL are saved as well (`log_t`, `log_dt`, `log_cfl`, `log_dvf`).
"""
import argparse
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import case

GRID = (case.NX, case.NY, case.NZ)
BOX = (case.LX, case.LY, case.LZ)
SPACING = tuple(L / n for L, n in zip(BOX, GRID))
BLOCK_HALO = 3            # vofBlocks.f90: offset_c

_STAGGER = {"ux": 0, "stx": 0, "phi0x": 0, "st0x": 0,
            "uy": 1, "sty": 1, "phi0y": 1, "st0y": 1,
            "uz": 2, "stz": 2, "phi0z": 2, "st0z": 2}


def field_shape(name, grid=GRID):
    shape = list(grid)
    if name in _STAGGER:
        shape[_STAGGER[name]] += 1
    return tuple(shape)


def read_field(snap, name, grid=GRID):
    """One field of one snapshot as an (nx[+1], ny[+1], nz[+1]) float64 array, x fastest."""
    shape = field_shape(name, grid)
    with open(os.path.join(snap, name), "rb") as f:
        n = int(np.fromfile(f, dtype="<i4", count=1)[0])
        if n != int(np.prod(shape)):
            raise ValueError(f"{snap}/{name}: {n} values, expected {shape}")
        a = np.fromfile(f, dtype="<f8", count=n)
    return a.reshape(shape, order="F")


def cell_velocity(snap, grid=GRID):
    """(ux, uy, uz) interpolated to cell centres, each (nx, ny, nz)."""
    ux = read_field(snap, "ux", grid)
    uy = read_field(snap, "uy", grid)
    uz = read_field(snap, "uz", grid)
    return (0.5 * (ux[:-1] + ux[1:]),
            0.5 * (uy[:, :-1] + uy[:, 1:]),
            0.5 * (uz[:, :, :-1] + uz[:, :, 1:]))


def snapshots(run):
    """[(folder, time, nb)] for every numbered output folder >= 1, sorted by time."""
    out = []
    for d in os.listdir(run):
        info = os.path.join(run, d, "info_restart")
        if d.isdigit() and int(d) > 0 and os.path.exists(info):
            with open(info) as f:
                lines = f.read().split()
            out.append((os.path.join(run, d), float(lines[0]), int(lines[1])))
    return sorted(out, key=lambda s: s[1])


def read_block(path):
    """(bubble number, global 0-based start index (3,), marker array) for one b<n> file."""
    with open(path, "rb") as f:
        head = np.fromfile(f, dtype="<i4", count=8)
        bn, idx = int(head[1]), head[2:8]
        shape = tuple(int(idx[2 * d + 1] - idx[2 * d] + 1 + 2 * BLOCK_HALO) for d in range(3))
        c0 = np.fromfile(f, dtype="<f8", count=int(np.prod(shape)))
    if c0.size != int(np.prod(shape)):
        raise ValueError(f"{path}: truncated block")
    start = np.array([idx[0], idx[2], idx[4]]) - BLOCK_HALO - 1      # 0-based, may be < 0
    return bn, start, c0.reshape(shape, order="F")


def bubbles(snap, nb, u_cc, grid=GRID):
    """Per-bubble centroid (wrapped), volume and marker-weighted velocity."""
    dV = np.prod(SPACING)
    pos = np.full((nb, 3), np.nan)
    vol = np.full(nb, np.nan)
    vel = np.full((nb, 3), np.nan)
    for b in range(1, nb + 1):
        path = os.path.join(snap, f"b{b}")
        if not os.path.exists(path):
            continue
        bn, start, cb = read_block(path)
        m = cb.sum()
        if m <= 0:
            vol[bn - 1] = 0.0
            continue
        ii = [start[d] + np.arange(cb.shape[d]) for d in range(3)]
        # unwrapped cell-centre coordinates -> centroid, then wrap the periodic x and z
        cen = []
        for d in range(3):
            xc = (ii[d] + 0.5) * SPACING[d]
            w = cb.sum(axis=tuple(a for a in range(3) if a != d))
            cen.append(float((w * xc).sum() / m))
        cen[0] %= BOX[0]
        cen[2] %= BOX[2]
        pos[bn - 1] = cen
        vol[bn - 1] = m * dV
        # the block may extend past the wall in y only through its halo, where cb == 0
        gi = np.ix_(ii[0] % grid[0], np.clip(ii[1], 0, grid[1] - 1), ii[2] % grid[2])
        vel[bn - 1] = [float((cb * u[gi]).sum() / m) for u in u_cc]
    return pos, vol, vel


def reduce_snapshot(snap, nb, grid=GRID):
    c = read_field(snap, "c", grid)
    u_cc = cell_velocity(snap, grid)
    dV = np.prod(SPACING)
    l = 1.0 - c
    sc, sl, n = c.sum(), l.sum(), c.size
    r = {}
    r["gas_volume"] = sc * dV
    r["u_gas"] = np.array([(c * u).sum() / sc for u in u_cc])
    r["u_mix"] = np.array([u.sum() / n for u in u_cc])
    r["u_liq"] = np.array([(l * u).sum() / sl for u in u_cc])
    r["rise_speed"] = -(r["u_gas"][0] - r["u_mix"][0])
    r["slip_speed"] = -(r["u_gas"][0] - r["u_liq"][0])
    cs = read_field(snap, "cs", grid)
    rho = case.RHO_G * cs + case.RHO_L * (1.0 - cs)
    r["momentum"] = np.array([(rho * u).sum() / n for u in u_cc])
    ux = u_cc[0]
    cy, ly = c.sum(axis=(0, 2)), l.sum(axis=(0, 2))
    r["alpha_y"] = cy / (grid[0] * grid[2])
    r["u_liq_y"] = (l * ux).sum(axis=(0, 2)) / ly
    with np.errstate(invalid="ignore", divide="ignore"):
        r["u_gas_y"] = np.where(cy > 1e-12, (c * ux).sum(axis=(0, 2)) / cy, np.nan)
    r["c_min"], r["c_max"] = float(c.min()), float(c.max())
    r["bubble_pos"], r["bubble_vol"], r["bubble_vel"] = bubbles(snap, nb, u_cc, grid)
    return r


def parse_log(path):
    """Per-step (t, dt, CFL, |vf-vf0|/vf0) from a TBFsolver stdout log."""
    t, dt, cfl, dvf = [], [], [], []
    num = r"([-+0-9.Ee]+)"
    with open(path, errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("t  ="):
                t.append(float(s.split("=")[1]))
            elif s.startswith("dt ="):
                dt.append(float(s.split("=")[1]))
            elif s.startswith("CFL max"):
                cfl.append(float(s.split("=")[1]))
            else:
                m = re.match(r"\|vf-vf0\|/vf0:\s*" + num, s)
                if m:
                    dvf.append(float(m.group(1)))
    k = min(len(t), len(dt), len(cfl))
    out = {"log_t": np.array(t[:k]), "log_dt": np.array(dt[:k]), "log_cfl": np.array(cfl[:k])}
    out["log_dvf"] = np.array(dvf[:k])
    return out


def unwrap_positions(pos):
    """Unwrap (nt, nb, 3) centroids in the periodic x and z across snapshots."""
    out = pos.copy()
    for d in (0, 2):
        L = BOX[d]
        step = np.diff(pos[:, :, d], axis=0)
        step -= L * np.round(step / L)
        out[1:, :, d] = pos[0, :, d] + np.nancumsum(step, axis=0)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run")
    ap.add_argument("--out", default="tbf_timeseries.npz")
    ap.add_argument("--every", type=int, default=1, help="use every n-th snapshot")
    a = ap.parse_args()

    snaps = snapshots(a.run)[:: a.every]
    if not snaps:
        raise SystemExit(f"no snapshots in {a.run}")
    rows = []
    for snap, t, nb in snaps:
        r = reduce_snapshot(snap, nb)
        r["t"] = t
        rows.append(r)
        print(f"t {t:9.4f}  V_gas {r['gas_volume']:.6f}  U_rise {r['rise_speed']:+.4f}  "
              f"U_slip {r['slip_speed']:+.4f}  <u>_mix_x {r['u_mix'][0]:+.2e}  "
              f"<rho u>_x {r['momentum'][0]:+.2e}  "
              f"c in [{r['c_min']:.1e}, {r['c_max']:.4f}]")

    ser = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    ser["bubble_pos_unwrapped"] = unwrap_positions(ser["bubble_pos"])
    ser["y"] = (np.arange(case.NY) + 0.5) * SPACING[1]
    ser["folder"] = np.array([int(os.path.basename(s[0])) for s in snaps])
    ser["grid"] = np.array(GRID)
    ser["box"] = np.array(BOX)
    ser["gas_volume_initial_exact"] = case.NB * np.pi / 6 * case.D ** 3
    log = os.path.join(a.run, "run.log")
    if os.path.exists(log):
        ser.update(parse_log(log))
    np.savez(a.out, **ser)
    v = ser["gas_volume"]
    print(f"wrote {a.out}: {len(rows)} snapshots, t {ser['t'][0]:.3f} .. {ser['t'][-1]:.3f}")
    print(f"  gas volume {v[0]:.6f} -> {v[-1]:.6f} (rel. change {v[-1]/v[0]-1:+.2e}); "
          f"exact spheres {ser['gas_volume_initial_exact']:.6f}")


if __name__ == "__main__":
    main()
