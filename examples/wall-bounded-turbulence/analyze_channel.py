#!/usr/bin/env python
"""Compare channel_dns.py stats against the MKM 1999 Re_tau=180 database.
Normalizes by the measured friction velocity (u_tau=1 for CPG; momentum-balance value for CFR)."""
import os, sys, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

STATS = sys.argv[1] if len(sys.argv) > 1 else "c128_stats.npz"
OUT = sys.argv[2] if len(sys.argv) > 2 else "channel_benchmark.png"
MKM = os.environ.get("MKM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mkm"))

d = np.load(STATS)
ny = int(d["NY"]); nu = float(d["nu"]); H = ny/2.0; yc = d["yc"]
utau = float(d["utau_cfr"]) if "utau_cfr" in d.files else 1.0
Re_tau = utau*H/nu
half = ny//2
yph = yc[:half]*utau/nu                       # y+ from lower wall, normalized by measured u_tau

def sym(a):    # symmetric about centerline
    return 0.5*(a[:half] + a[::-1][:half])
def wall_uv(a):  # -<u'v'> in wall frame (antisymmetric field -> both walls positive)
    return 0.5*(a[::-1][:half] - a[:half])

Up   = sym(d["prof_U"])/utau
urms = np.sqrt(np.abs(sym(d["prof_uu"])))/utau
vrms = np.sqrt(np.abs(sym(d["prof_vv"])))/utau
wrms = np.sqrt(np.abs(sym(d["prof_ww"])))/utau
uvp  = wall_uv(d["prof_uv"])/utau**2

# MKM Re_tau=180
m_mean = np.loadtxt(f"{MKM}/chan180.means", comments="#")
m_rey  = np.loadtxt(f"{MKM}/chan180.reystress", comments="#")
m_yp = m_mean[:, 1]; m_U = m_mean[:, 2]; mr_yp = m_rey[:, 1]
m_urms = np.sqrt(m_rey[:, 2]); m_vrms = np.sqrt(m_rey[:, 3]); m_wrms = np.sqrt(m_rey[:, 4]); m_uv = -m_rey[:, 5]

fig, ax = plt.subplots(2, 2, figsize=(11, 8.5))
a = ax[0, 0]
a.semilogx(m_yp[m_yp > 0], m_U[m_yp > 0], "k-", lw=2, label="MKM 1999")
a.semilogx(yph, Up, "o", ms=3, color="C0", label="peclet.flow")
yy = np.logspace(0, np.log10(max(Re_tau, 180)), 50)
a.semilogx(yy, yy, "k:", lw=0.8, label=r"$U^+=y^+$")
a.semilogx(yy[yy > 8], (1/0.41)*np.log(yy[yy > 8]) + 5.2, "k--", lw=0.8, label=r"log law")
a.set_xlabel(r"$y^+$"); a.set_ylabel(r"$U^+$"); a.set_title("Mean velocity"); a.legend(fontsize=8); a.set_xlim(1, 200)

a = ax[0, 1]
for prof, mprof, c, lab in [(urms, m_urms, "C0", "u"), (vrms, m_vrms, "C1", "v"), (wrms, m_wrms, "C2", "w")]:
    a.plot(mr_yp, mprof, "-", color=c, lw=2)
    a.plot(yph, prof, "o", ms=2.5, color=c, label=fr"${lab}_{{rms}}^+$")
a.set_xlabel(r"$y^+$"); a.set_ylabel("rms$^+$"); a.set_title("Fluctuations (line=MKM, pts=flow)")
a.legend(fontsize=8); a.set_xlim(0, 180)

a = ax[1, 0]
a.plot(mr_yp, m_uv, "k-", lw=2, label=r"MKM $-\langle u'v'\rangle^+$")
a.plot(yph, uvp, "o", ms=3, color="C3", label="flow")
dUp = np.gradient(Up, yph)
a.plot(yph, uvp + dUp, "C5--", lw=1, label="total stress")
a.plot(yph, 1 - yph/Re_tau, "k:", lw=0.8, label=r"$1-y/H$")
a.set_xlabel(r"$y^+$"); a.set_ylabel("stress$^+$"); a.set_title("Stress balance"); a.legend(fontsize=8); a.set_xlim(0, 180)

a = ax[1, 1]
ts = d["ts"]
a.plot(ts[:, 1], ts[:, 5], "C0-", label=r"$u_{rms,pk}$")
a.plot(ts[:, 1], ts[:, 7], "C2-", label=r"tke$_{pk}$")
a.plot(ts[:, 1], ts[:, 6]*10, "C3-", label=r"$-\langle u'v'\rangle_{pk}\times10$")
a.set_xlabel(r"$t^+$"); a.set_title("Turbulence time series"); a.legend(fontsize=8)

plt.suptitle(f"Channel DNS  {d['NX']}x{d['NY']}x{d['NZ']}  Delta+={float(d['Dplus']):.2f}  "
             f"Re_tau(meas)={Re_tau:.0f} (MKM 178)  Lx+={float(d['Lxp'])*utau:.0f} Lz+={float(d['Lzp'])*utau:.0f}  nacc={int(d.get('nacc',0))}")
plt.tight_layout(); plt.savefig(OUT, dpi=110); print("wrote", OUT)

print(f"measured u_tau = {utau:.4f}   Re_tau = {Re_tau:.1f}   (MKM 178.1)")
print(f"-<u'v'>+ peak   flow={uvp.max():.3f}   MKM={m_uv.max():.3f}   ({100*uvp.max()/m_uv.max():.0f}%)")
print(f"u_rms+   peak   flow={urms.max():.3f}   MKM={m_urms.max():.3f}   ({100*urms.max()/m_urms.max():.0f}%)")
print(f"centerline U+  flow={Up[-1]:.2f}   MKM=18.30")
mask = (yph > 30) & (yph < min(120, Re_tau*0.7))
if mask.sum() > 3:
    p = np.polyfit(np.log(yph[mask]), Up[mask], 1)
    print(f"log-law fit: kappa={1/p[0]:.3f}  B={p[1]:.2f}   (MKM 0.41, 5.2)")
