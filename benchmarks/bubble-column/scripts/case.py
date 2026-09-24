"""The bubble-column benchmark case — ONE definition shared by the peclet and TBFsolver runs.

A vertical, infinitely tall (periodic) bubble column between two plane walls: gravity along -x
... in TBFsolver's convention "g is along x" with bubbles rising towards -x; we keep that frame in
both codes so the raw fields compare index-for-index.

    x   vertical, periodic, length LX          (TBFsolver: the only r2c-FFT direction)
    y   wall-normal, no-slip walls at 0, LY    (TBFsolver's FAST_MODE Poisson: tridiagonal in y)
    z   spanwise, periodic, length LZ

A closed (batch) column. The mean weight of the mixture is carried by a uniform mean pressure
gradient -<rho> g, so the momentum source per unit volume is (rho - <rho>) g along +x: liquid is
pushed down (+x), gas up (-x). In addition the net VOLUME flux is held at exactly zero: after
every step one uniform correction du = -<u_x> (the volume mean over the x-faces) is added to
every u_x face (TBFsolver `flowCtrl 2` with `flow_rate 0`, `setFlowRate`), so the liquid can
only circulate, never flow through the column. Without that constraint (`flowCtrl 3`: pressure
gradient fixed at the weight, flux free) the liquid descending along the walls feels an upward
wall friction that nothing balances, and the column develops a growing net upflow (measured
d<rho u>_x/dt = -0.0056 over t = 2..7) until the net wall shear vanishes: not a batch column.

Bubbles: Loisy, Naso & Spelt, J. Fluid Mech. 816 (2017) 94, case E1 — Archimedes 29.9, Bond 2.0
(weakly ellipsoidal, isolated Re0 ~ 31 from Loth 2008), with rho_g/rho_l = mu_g/mu_l = 0.02 as in
Bunner & Tryggvason (2002). Units: D = rho_l = g = 1.
"""
import numpy as np

# --- physics (D = rho_l = g = 1) ----------------------------------------------------------
AR = 29.9                      # Archimedes number  sqrt(rho_l (rho_l - rho_g) g D^3) / mu_l
BO = 2.0                       # Bond (Eotvos) number (rho_l - rho_g) g D^2 / sigma
RHO_L = 1.0
RHO_G = 0.02
D = 1.0
G = 1.0
MU_L = np.sqrt(RHO_L * (RHO_L - RHO_G) * G * D ** 3) / AR
MU_G = 0.02 * MU_L
SIGMA = (RHO_L - RHO_G) * G * D ** 2 / BO
U_REF = np.sqrt(G * D)         # the gravitational velocity scale; isolated U0 ~ Re0 mu/(rho D) ~ 1.03

# --- geometry -----------------------------------------------------------------------------
LX, LY, LZ = 8.0, 6.0, 4.0     # vertical (periodic), wall-normal (walls), spanwise (periodic)
CELLS_PER_D = 16
NX, NY, NZ = int(LX * CELLS_PER_D), int(LY * CELLS_PER_D), int(LZ * CELLS_PER_D)   # 128 x 96 x 64
H = D / CELLS_PER_D

# --- bubbles: a 4 x 2 x 2 array (x fastest, TBFsolver's loop order), perturbed ---------------
NBX, NBY, NBZ = 4, 2, 2
NB = NBX * NBY * NBZ
R = 0.5 * D
SEED = 20260924
PERTURB = 0.25                 # fraction of the free gap between neighbouring bubbles


def bubble_centres():
    """Deterministic perturbed array; (NB, 3) in physical units, TBFsolver's i-fastest order."""
    rng = np.random.default_rng(SEED)
    dxb, dyb, dzb = LX / NBX, LY / NBY, LZ / NBZ
    gaps = np.array([dxb, dyb, dzb]) - D
    out = []
    for k in range(NBZ):
        for j in range(NBY):
            for i in range(NBX):
                c = np.array([(i + 0.5) * dxb, (j + 0.5) * dyb, (k + 0.5) * dzb])
                c += (rng.random(3) - 0.5) * PERTURB * gaps
                out.append(c)
    return np.array(out)


VOID_FRACTION = NB * np.pi / 6 * D ** 3 / (LX * LY * LZ)

# --- run control --------------------------------------------------------------------------
T_END = 60.0                   # ~60 D/U0
T_STATS = 20.0                 # statistics window [T_STATS, T_END]
DT_OUT = 1.0                   # snapshot interval (TBFsolver dtout; peclet sampling)


def summary():
    return (f"Ar {AR}, Bo {BO}, rho_g/rho_l {RHO_G}, mu_l {MU_L:.6f}, mu_g {MU_G:.4e}, "
            f"sigma {SIGMA:.4f}; box {LX}x{LY}x{LZ} D, grid {NX}x{NY}x{NZ} (D/h = {CELLS_PER_D}); "
            f"{NB} bubbles, void fraction {100*VOID_FRACTION:.2f} %")


if __name__ == "__main__":
    print(summary())
    for c in bubble_centres():
        print(f"{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}")
