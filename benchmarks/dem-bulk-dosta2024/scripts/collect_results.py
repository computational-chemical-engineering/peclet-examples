#!/usr/bin/env python
"""Collect every benchmark result into peclet-examples/benchmarks/dem-bulk-dosta2024/data/.

One npz per (case, code[, config]) with uniform keys, plus timings.json.
Idempotent: reruns overwrite. Skips missing sources with a note.
"""
import json
import os
import shutil

import numpy as np

BENCH = os.path.expanduser("~/Codes/dem-bench")
SCRATCH = ("/tmp/claude-1003/-home-frankp-Codes-suite/9e9b807a-7a8a-4948-a080-545a0f831797/"
           "scratchpad/dosta2024/SupplementaryMaterial/Scripts")
OUT = os.path.expanduser("~/Codes/peclet-examples/benchmarks/dem-bulk-dosta2024/data")
os.makedirs(OUT, exist_ok=True)

Z0 = {"large": -0.0554222, "small": -0.0593008}
timings = {}
notes = []


def put(name, **arrs):
    np.savez_compressed(os.path.join(OUT, name + ".npz"), **arrs)


def wall_of(npz):
    return float(npz["wall_s"]) if "wall_s" in npz.files else None


# ---- case 3: impact trajectories ----
# NOTE ordering: the *_pp (exact per-pair materials) runs come LAST so they overwrite the
# approximated-material runs under the featured code names; the approximated runs are also
# kept under their own *_approx names for the sensitivity note.
for n in (25, 50, 100):
    for tag, code in ((f"case3_{n}k_peclet_jac", f"case3_{n}k_peclet_jacobi"),
                      (f"case3_{n}k_peclet", f"case3_{n}k_peclet_onesided"),
                      (f"case3_{n}k_peclet_sympgs", f"case3_{n}k_peclet_sympgs_approx"),
                      (f"case3_{n}k_peclet_onesided", f"case3_{n}k_peclet_onesided_approx"),
                      (f"case3_{n}k_peclet_sympgs", f"case3_{n}k_peclet_sympgs"),
                      (f"case3_{n}k_peclet_onesided", f"case3_{n}k_peclet_onesided"),
                      (f"case3_{n}k_peclet_sympgs_pp", f"case3_{n}k_peclet_sympgs"),
                      (f"case3_{n}k_peclet_onesided_pp", f"case3_{n}k_peclet_onesided"),
                      (f"case3_{n}k_musen", f"case3_{n}k_musen")):
        src = f"{BENCH}/peclet/{tag}.npz"
        if os.path.exists(src):
            d = np.load(src)
            put(code, t=d["t"], z=d["z"])
            w = wall_of(d)
            if w:
                timings[code] = w
    lig = f"{BENCH}/runs/liggghts/penetration_{n:03d}k/post/height.dat"
    if os.path.exists(lig):
        z = np.loadtxt(lig)
        t = np.arange(len(z)) * 100 * 5e-7
        put(f"case3_{n}k_liggghts", t=t, z=z)

timings["case3_25k_liggghts"] = 1839.0
timings["case3_50k_liggghts"] = 678.0
timings["case3_100k_liggghts"] = 913.0
timings["case3_25k_musen"] = 1346.0

# MUSEN wall times from each case's sim log ("Elapsed time [d:h:m:s]: 00:03:18:13")
import re
MUSEN_KEY = {"penetration_050k": "case3_50k_musen", "penetration_100k": "case3_100k_musen",
             "silo_large_m1": "case1_large_M1_musen", "silo_small_m1": "case1_small_M1_musen",
             "mixer": "case2_musen"}
for case, key in MUSEN_KEY.items():
    log = f"{SCRATCH}/MUSEN/cases/{case}/musen_sim.log"
    if os.path.exists(log):
        m = re.findall(r"Elapsed time \[d:h:m:s\]: (\d+):(\d+):(\d+):(\d+)", open(log).read())
        if m:
            d, h, mn, s = map(int, m[-1])
            timings[key] = float(((d * 24 + h) * 60 + mn) * 60 + s)

# ---- case 1: silo curves ----
for f, code in (("case1_large_M1_onesided", "case1_large_M1_peclet_onesided"),
                ("case1_large_M1_sympgs", "case1_large_M1_peclet_sympgs"),
                ("case1_small_M1_sympgs", "case1_small_M1_peclet_sympgs"),
                ("case1_large_M2_onesided", "case1_large_M2_peclet_onesided"),
                ("case1_small_M1_onesided", "case1_small_M1_peclet_onesided"),
                ("case1_small_M2_onesided", "case1_small_M2_peclet_onesided"),
                ("case1_large_M1_musen", "case1_large_M1_musen"),
                ("case1_small_M1_musen", "case1_small_M1_musen")):
    src = f"{BENCH}/peclet/{f}.npz"
    if os.path.exists(src):
        d = np.load(src)
        put(code, t=d["t"], count=d["count"])
        w = wall_of(d)
        if w:
            timings[code] = w
    else:
        notes.append(f"missing {f}")

# MUSEN silo exports (large + small): count active particles above the orifice lip per frame.
# Exited (deactivated) particles are written as exact (0,0,0) -- filter them.
def musen_silo(case, z0):
    path = f"{SCRATCH}/MUSEN/cases/{case}/{case}_export.txt"
    if not os.path.exists(path):
        return None
    counts = {}
    with open(path) as fh:
        for line in fh:
            v = line.split()
            i = 5
            while i + 5 < len(v) + 1:
                if v[i] == "2" and v[i + 2] == "12":
                    t = round(float(v[i + 1]), 1)
                    x, y, z = float(v[i + 3]), float(v[i + 4]), float(v[i + 5])
                    if z > z0 and not (x == 0.0 and y == 0.0 and z == 0.0):
                        counts[t] = counts.get(t, 0) + 1
                    i += 6
                else:
                    i += 1
    ts = np.array(sorted(counts))
    return ts, np.array([counts[t] for t in ts])

r = musen_silo("silo_small_m1", Z0["small"])
if r:
    put("case1_small_M1_musen", t=r[0], count=r[1])

# MUSEN mixer export: zone counts + species COM from coordinates (radius col 3: 0.001 = M1)
def musen_mixer():
    path = f"{SCRATCH}/MUSEN/cases/mixer/mixer_export.txt"
    if not os.path.exists(path):
        return False
    frames = {}
    with open(path) as fh:
        for line in fh:
            v = line.split()
            if len(v) < 11:
                continue
            try:
                rad = float(v[3])
            except ValueError:
                continue
            m1 = rad < 0.0015
            i = 5
            while i + 5 < len(v) + 1:
                if v[i] == "2" and v[i + 2] == "12":
                    t = round(float(v[i + 1]), 1)
                    x, z = float(v[i + 3]), float(v[i + 5])
                    fr = frames.setdefault(t, [0, 0, 0, 0, [], []])
                    if x > 0 and z > 0:
                        fr[0 if m1 else 1] += 1
                    if x < 0 and z < 0:
                        fr[2 if m1 else 3] += 1
                    (fr[4] if m1 else fr[5]).append((x, float(v[i + 4]), z))
                    i += 6
                else:
                    i += 1
    ts = sorted(frames)
    z1m1 = [frames[t][0] for t in ts]
    z1m2 = [frames[t][1] for t in ts]
    z2m1 = [frames[t][2] for t in ts]
    z2m2 = [frames[t][3] for t in ts]
    com1 = [np.mean(frames[t][4], axis=0) for t in ts]
    com2 = [np.mean(frames[t][5], axis=0) for t in ts]
    put("case2_musen", t=np.array(ts), z1_m1=z1m1, z1_m2=z1m2, z2_m1=z2m1, z2_m2=z2m2,
        com_m1=np.array(com1), com_m2=np.array(com2))
    return True

musen_mixer()

# LIGGGHTS silo: residence.dat = count(all, r1) every 100 steps (dt 1.5e-6)
lig = f"{BENCH}/runs/liggghts/silo_large_m1/post/residence.dat"
if os.path.exists(lig):
    N = np.loadtxt(lig)
    t = np.arange(len(N)) * 100 * 1.5e-6
    put("case1_large_M1_liggghts", t=t, count=N)

# ---- case 2: mixer ----
for f, code in (("case2_peclet_onesided", "case2_peclet_onesided"),
                ("case2_peclet_sympgs", "case2_peclet_sympgs")):
    src = f"{BENCH}/peclet/{f}.npz"
    if os.path.exists(src):
        d = np.load(src)
        put(code, **{k: d[k] for k in d.files})
        w = wall_of(d)
        if w:
            timings[code] = w
    else:
        notes.append(f"missing {f}")

# LIGGGHTS mixer: region dumps radius-per-particle in zones r1/r2 every 0.1 s
import glob
lig_dir = f"{BENCH}/runs/liggghts/mixer/post"
r1 = sorted(glob.glob(f"{lig_dir}/region1_*.dat"),
            key=lambda p: int(p.split("_")[-1].split(".")[0]))
if r1:
    def zone_counts(files):
        ts, m1, m2 = [], [], []
        for p in files:
            step = int(p.split("_")[-1].split(".")[0])
            with open(p) as fh:
                lines = fh.readlines()
            # LAMMPS dump: header 9 lines, then one radius per row
            radii = np.array([float(x) for x in lines[9:]]) if len(lines) > 9 else np.array([])
            ts.append(step * 8e-7)
            m1.append(int((radii < 0.0015).sum()))
            m2.append(int((radii > 0.0015).sum()))
        return np.array(ts), np.array(m1), np.array(m2)

    t1, z1m1, z1m2 = zone_counts(r1)
    r2 = sorted(glob.glob(f"{lig_dir}/region2_*.dat"),
                key=lambda p: int(p.split("_")[-1].split(".")[0]))
    t2, z2m1, z2m2 = zone_counts(r2)
    put("case2_liggghts", t=t1, z1_m1=z1m1, z1_m2=z1m2, z2_m1=z2m1, z2_m2=z2m2)
    timings["case2_liggghts"] = 15855.0

with open(os.path.join(OUT, "timings.json"), "w") as fh:
    json.dump(timings, fh, indent=1, sort_keys=True)
print("collected ->", OUT)
print("timings:", len(timings), "entries")
for n in notes:
    print("NOTE:", n)
