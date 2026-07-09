#!/usr/bin/env python
"""Overlay several channel_dns.py stats files (a resolution study) against MKM 1999 Re_tau=180."""
import os, sys, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

MKM = os.environ.get("MKM_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mkm"))
files = sys.argv[1:-1]; OUT = sys.argv[-1]

def load(fn):
    d = np.load(fn); ny = int(d["NY"]); nu = float(d["nu"]); H = ny/2.0; yc = d["yc"]
    utau = float(d["utau_cfr"]) if "utau_cfr" in d.files else 1.0
    half = ny//2
    sym = lambda a: 0.5*(a[:half] + a[::-1][:half])
    wuv = lambda a: 0.5*(a[::-1][:half] - a[:half])
    return dict(yp=yc[:half]*utau/nu, U=sym(d["prof_U"])/utau,
                urms=np.sqrt(np.abs(sym(d["prof_uu"])))/utau,
                vrms=np.sqrt(np.abs(sym(d["prof_vv"])))/utau,
                wrms=np.sqrt(np.abs(sym(d["prof_ww"])))/utau,
                uv=wuv(d["prof_uv"])/utau**2, Dp=float(d["Dplus"]),
                Retau=utau*H/nu, ny=ny)

runs = sorted((load(f) for f in files), key=lambda r: -r["Dp"])
m_mean = np.loadtxt(f"{MKM}/chan180.means", comments="#")
m_rey  = np.loadtxt(f"{MKM}/chan180.reystress", comments="#")

fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
a = ax[0]
a.semilogx(m_mean[m_mean[:,1]>0,1], m_mean[m_mean[:,1]>0,2], "k-", lw=2.5, label="MKM 1999")
for r in runs:
    a.semilogx(r["yp"], r["U"], "-o", ms=2, label=fr"$\Delta^+$={r['Dp']:.1f} (Re$_\tau$={r['Retau']:.0f})")
a.set_xlabel(r"$y^+$"); a.set_ylabel(r"$U^+$"); a.set_title("Mean velocity"); a.legend(fontsize=8); a.set_xlim(1, 200)

a = ax[1]
a.plot(m_rey[:,1], np.sqrt(m_rey[:,2]), "k-", lw=2.5, label="MKM $u_{rms}$")
for r in runs:
    a.plot(r["yp"], r["urms"], "-o", ms=2, label=fr"$\Delta^+$={r['Dp']:.1f}")
a.set_xlabel(r"$y^+$"); a.set_ylabel(r"$u_{rms}^+$"); a.set_title("Streamwise fluctuations"); a.legend(fontsize=8); a.set_xlim(0, 180)

a = ax[2]
a.plot(m_rey[:,1], -m_rey[:,5], "k-", lw=2.5, label="MKM")
for r in runs:
    a.plot(r["yp"], r["uv"], "-o", ms=2, label=fr"$\Delta^+$={r['Dp']:.1f}")
a.set_xlabel(r"$y^+$"); a.set_ylabel(r"$-\langle u'v'\rangle^+$"); a.set_title("Reynolds shear stress"); a.legend(fontsize=8); a.set_xlim(0, 180)

plt.suptitle("Channel DNS at Re_tau=180: convergence toward MKM as grid refines (upwind SOU, isotropic grid)")
plt.tight_layout(); plt.savefig(OUT, dpi=110); print("wrote", OUT)
for r in runs:
    print(f"  Delta+={r['Dp']:.2f}  Re_tau={r['Retau']:5.1f}  "
          f"uv_pk={r['uv'].max():.3f}  urms_pk={r['urms'].max():.2f}  U_cl={r['U'][-1]:.1f}")
