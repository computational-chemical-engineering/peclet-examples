"""Flow through the Pall-ring pack, physical units (D = 1, rho = 1, superficial U = 0.1), for rendering.

python sim.py RES NSTEP OUT MODE      MODE = stokes | re<N> | re<N>io   (Re_D = rho U D / mu)
Periodic in x, z. stokes / re<N>: periodic in y too, driven by a body force; re<N>io: uniform inflow at -y and
outflow at +y (the poster's Re = 100 case). The bed (extent -0.027..5.981 in pack coords) sits 2.1 D above the
domain floor, 1.5 D of fluid above it. The last 30 % of steps are time-averaged (identical to the final field if the flow is steady).
"""
import os, sys, time, numpy as np
import peclet.flow as sdflow
PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pall-ring-packing", "pall_ring_pack.npz")
RES = int(sys.argv[1]); NSTEP = int(sys.argv[2]); OUT = sys.argv[3]; MODE = sys.argv[4]
z = np.load(PACK)
pos, quat = z["positions"].astype(float), z["quaternions"].astype(float)
ni, nr, root, L = z["node_ints"], z["node_reals"], int(z["home_root"]), float(z["box"][0])
BED_LO, BED_HI = -0.0271, 5.9811
YSHIFT = 2.1 - BED_LO                                  # y_domain = y_pack + YSHIFT
h = 1.0 / RES; NX = int(round(L * RES)); NY = 32 * int(np.ceil((2.1 + BED_HI - BED_LO + 1.5) * RES / 32)); Ly = NY * h   # MG-friendly
s = sdflow.Solver((NX, NY, NX), extent=(NX * h, Ly, NX * h))
RHO, U_T = 1.0, 0.1
IO = False
if MODE == "stokes":
    MU, ADV, dt = 0.1, False, 0.1
else:
    IO = MODE.endswith("io"); MODE_RE = MODE[2:-2] if IO else MODE[2:]
    MU, ADV = RHO * U_T / float(MODE_RE), True
    dt = 0.2 * h / (3 * U_T)
if IO:                                                 # uniform inlet at -y, outflow at +y, periodic in x, z
    s.set_domain_bc("-y", "inflow", (0.0, U_T, 0.0)); s.set_domain_bc("+y", "outflow")
ii = np.zeros((len(pos), 2), np.int32); ii[:, 0] = root; ii[:, 1] = -1
ir = np.zeros((len(pos), 17)); ir[:, 0] = pos[:, 0]; ir[:, 1] = pos[:, 1] + YSHIFT; ir[:, 2] = pos[:, 2]
ir[:, 3:7] = quat; ir[:, 7] = 1.0
s.set_rho(RHO); s.set_mu(MU); s.set_dt(dt); s.set_advection(ADV)
s.diagnostics.set_velocity_solver_params(60); s.set_pressure_solver_params(20)
s.set_pressure_multigrid(True, levels=4)
s.set_scene(np.asarray(ni, np.int32), np.asarray(nr, float), ii.ravel(), ir.ravel(), periodic=True)
s.set_solid_from_scene(True)
F = 195.0 * MU * U_T + 2.8 * RHO * U_T ** 2            # Ergun-sized first guess, then a damped controller
if not IO: s.set_body_force((0.0, F, 0.0))
acc = None; nacc = 0; t0 = time.time(); probe = []
for k in range(NSTEP):
    s.step()
    if k % 100 == 99:
        U = float(np.asarray(s.get_v()).mean())
        if k < NSTEP * 0.5 and not IO:
            F *= min(1.5, max(0.67, (U_T / max(U, 1e-12)) ** 0.5)); s.set_body_force((0.0, F, 0.0))
        vv = np.asarray(s.get_v()); probe.append([vv[NX // 2, int(1.0 * RES), NX // 2], vv[NX // 3, int(4.5 * RES), NX // 4]])
        print("step %d  U=%.5e  F=%.4e  Re=%.2f  probes %.5f %.5f  %.0fs"
              % (k + 1, U, F, RHO * U / MU, probe[-1][0], probe[-1][1], time.time() - t0), flush=True)
    if k >= 0.7 * NSTEP and k % 10 == 0:
        cur = [np.asarray(g()).copy() for g in (s.get_u, s.get_v, s.get_w)]
        acc = cur if acc is None else [a + c for a, c in zip(acc, cur)]; nacc += 1
u, v, w = (a / nacc for a in acc)
uf, vf, wf = (np.asarray(g()) for g in (s.get_u, s.get_v, s.get_w))
print("mean-vs-final max|dv|/U = %.3e  (0 for a steady flow)" % (np.abs(vf - v).max() / U_T))
np.savez_compressed(OUT, u=u, v=v, w=w, cells=(NX, NY, NX), h=h, yshift=YSHIFT, Re=RHO * float(v.mean()) / MU,
                    mode=MODE, F=F, mu=MU, probe=np.asarray(probe))
