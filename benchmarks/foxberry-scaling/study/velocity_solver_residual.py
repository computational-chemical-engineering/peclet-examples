#!/usr/bin/env python
"""Momentum solve on the FoxBerry walls/inlet bed, single rank (init_mpi path): the production
RB-GS (update criterion) vs RB-GS and the mixed velocity MG under the RESIDUAL stop
max|b - A u| <= VRES * max|b|. Reports cost (s/step, sweeps or V-cycles per step), the exit
residual, and the error against an RB-GS reference run to a tight update tolerance.

Usage: PYTHONPATH=<mpi flow build> python velocity_solver_residual.py [--gn 96] [--steps 3]
"""
import argparse, json, os, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "..", "foxberry_bench.py")
ap = argparse.ArgumentParser()
ap.add_argument("--gn", type=int, default=96)
ap.add_argument("--steps", type=int, default=3)
ap.add_argument("--threads", type=int, default=8)
ap.add_argument("--np", type=int, default=1)
ap.add_argument("--levels", default="3,5")
ap.add_argument("--vres", default="1e-3,1e-5")
ap.add_argument("--out", default=None)
args = ap.parse_args()
args.out = args.out or os.path.join(HERE, f"velocity_residual_walls_{args.gn}_np{args.np}")
os.makedirs(args.out, exist_ok=True)
base = dict(os.environ, CASE="packed", BCMODE="foxberry", BED="walls",
            PACK=os.path.join(HERE, "..", "results", "packing_foxberry_walls_n5000_phi0.45_s0.npz"),
            GN=str(args.gn), NSTEPS=str(args.steps), WARMUP="0", OMP_NUM_THREADS=str(args.threads),
            OMP_PROC_BIND="false", TELESCOPE="1", MGLEVELS="8")

def run(tag, **env):
    e = dict(base); e.update({k: str(v) for k, v in env.items()})
    e["OUT"] = os.path.join(args.out, f"{tag}.json"); e["SAVEU"] = os.path.join(args.out, f"{tag}.npy")
    with open(os.path.join(args.out, f"{tag}.log"), "w") as fh:
        subprocess.run(["mpirun", "--oversubscribe", "-np", str(args.np), sys.executable, BENCH],
                       env=e, stdout=fh, stderr=subprocess.STDOUT)
    return json.load(open(e["OUT"]))

rows = []
def rec(tag, d):
    u = np.load(os.path.join(args.out, f"{tag}.npy")) if args.np == 1 else None
    err = float(np.max(np.abs(u - uref))) / umax if u is not None else float("nan")
    r = (tag, d["ms_per_step"] / 1e3, d["momentum_sweeps_per_step"], d.get("momentum_residual_mean", -1),
         d.get("momentum_residual_max", -1), err, d["phase_seconds_per_step"]["momentum"]["max"])
    rows.append(r)
    print(f"  {r[0]:18s} {r[1]:7.2f} s/step  momentum {r[6]:6.2f} s  sweeps|cycles {r[2]:7.1f}  "
          f"resid {r[3]:.1e} (max {r[4]:.1e})  err {r[5]:.2e}", flush=True)

d = run("ref", VSWEEPS=5000, VRTOL=1e-9)
uref = np.load(os.path.join(args.out, "ref.npy")) if args.np == 1 else None
umax = float(np.max(np.abs(uref))) if uref is not None else 1.0
rec("ref", d)
rec("rbgs_update", run("rbgs_update"))
for vr in args.vres.split(","):
    rec(f"rbgs_res{vr}", run(f"rbgs_res{vr}", VRES=vr))
    for L in [int(v) for v in args.levels.split(",")]:
        rec(f"vmg_L{L}_res{vr}", run(f"vmg_L{L}_res{vr}", VMG=L, VMGCYCLES=40, VRES=vr))
print(f"\nsummary ({args.gn}^3, {args.steps} steps, np={args.np}): tag, s/step, momentum s, sweeps|cycles, resid mean, resid max, rel err vs ref")
for r in rows:
    print(f"  {r[0]:18s} {r[1]:7.2f} {r[6]:7.2f} {r[2]:8.1f} {r[3]:9.1e} {r[4]:9.1e} {r[5]:9.2e}")
json.dump(rows, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
