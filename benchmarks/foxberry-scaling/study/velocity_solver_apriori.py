#!/usr/bin/env python
"""A-priori study of the momentum (implicit diffusion) solve on the FoxBerry bed, single rank.

Questions: (1) how far from converged is the production RB-GS at its 200-sweep cap, (2) does the
staircase velocity multigrid reach a converged momentum solve cheaper, (3) how many LEVELS does it
need -- i.e. would the velocity hierarchy need telescoping under MPI, or does a shallow hierarchy
already do. The reference is RB-GS run to a tight update tolerance (20000-sweep cap).

Periodic bed + periodic BCs (the only IBM path the velocity MG supports today), GN^3, a few steps
from rest at the FoxBerry dt (nu*dt/dx^2 ~ 4e4 at 384^3; the box-relative diffusion length
sqrt(nu dt)/L = 0.51 is resolution-independent, so the regime is the benchmark's).

Usage: PYTHONPATH=<mpi flow build> python velocity_solver_apriori.py [--gn 128] [--steps 3]
"""
import argparse, json, os, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "..", "foxberry_bench.py")
ap = argparse.ArgumentParser()
ap.add_argument("--gn", type=int, default=128)
ap.add_argument("--steps", type=int, default=3)
ap.add_argument("--threads", type=int, default=16)
ap.add_argument("--out", default=None)
ap.add_argument("--levels", default="2,3,4,5,6")
ap.add_argument("--cycles", default="1,2,4,8")
ap.add_argument("--bc", default="walls", choices=["walls", "periodic"],
                help="walls = FoxBerry BCs (inlet/outlet/walls, wall-confined bed); periodic = stand-in")
ap.add_argument("--vtol", default="1e-3", help="update tolerance for both RB-GS and the V-cycles")
ap.add_argument("--np", type=int, default=1)
args = ap.parse_args()
args.out = args.out or os.path.join(HERE, f"velocity_apriori_{args.bc}_{args.gn}")
os.makedirs(args.out, exist_ok=True)

bed = "walls" if args.bc == "walls" else "periodic"
base = dict(os.environ, CASE="packed", BCMODE="foxberry" if args.bc == "walls" else "periodic", BED=bed,
            PACK=os.path.join(HERE, "..", "results", f"packing_foxberry_{bed}_n5000_phi0.45_s0.npz"),
            VRTOL=args.vtol,
            GN=str(args.gn), NSTEPS=str(args.steps), WARMUP="0", OMP_NUM_THREADS=str(args.threads),
            OMP_PROC_BIND="false", TELESCOPE="1", MGLEVELS="8")

def run(tag, **env):
    e = dict(base); e.update({k: str(v) for k, v in env.items()})
    e["OUT"] = os.path.join(args.out, f"{tag}.json"); e["SAVEU"] = os.path.join(args.out, f"{tag}.npy")
    log = os.path.join(args.out, f"{tag}.log")
    t0 = time.time()
    with open(log, "w") as fh:
        subprocess.run(["mpirun", "--oversubscribe", "-np", str(args.np), sys.executable, BENCH], env=e, stdout=fh, stderr=subprocess.STDOUT)
    d = json.load(open(e["OUT"]))
    print(f"  {tag:14s} {d['ms_per_step']/1e3:8.2f} s/step  sweeps/step {d.get('momentum_sweeps_per_step', 0):7.1f}"
          f"  pressure it {d['pressure_iters_per_step']:5.1f}   ({time.time()-t0:.0f} s)", flush=True)
    return d

print(f"reference: RB-GS to update-tol 1e-9 (cap 5000)")
run("ref", VSWEEPS=5000, VRTOL=1e-9)
uref = np.load(os.path.join(args.out, "ref.npy"))
def err(tag):
    u = np.load(os.path.join(args.out, f"{tag}.npy"))
    return float(np.max(np.abs(u - uref))) / float(np.max(np.abs(uref)))
rows = []
print("production RB-GS (cap 200, update-tol 1e-3):")
d = run("rbgs200"); rows.append(("rbgs200", d["ms_per_step"]/1e3, d["momentum_sweeps_per_step"], err("rbgs200")))
print(f"     rel max|u-uref| = {rows[-1][3]:.3e}")
for L in [int(v) for v in args.levels.split(",")]:
    for nc in [int(v) for v in args.cycles.split(",")]:
        tag = f"vmg_L{L}_c{nc}"
        d = run(tag, VMG=L, VMGCYCLES=nc)
        rows.append((tag, d["ms_per_step"]/1e3, d.get("momentum_sweeps_per_step", 0), err(tag)))
        print(f"     rel max|u-uref| = {rows[-1][3]:.3e}")
print("\nsummary (rel max|u - u_ref| after %d steps, %d^3):" % (args.steps, args.gn))
print(f"  {'config':14s} {'s/step':>8s} {'sweeps':>8s} {'rel err':>10s}")
for r in rows:
    print(f"  {r[0]:14s} {r[1]:8.2f} {r[2]:8.1f} {r[3]:10.3e}")
json.dump(rows, open(os.path.join(args.out, "summary.json"), "w"), indent=1)
