#!/usr/bin/env python
"""Backfill `pressure_iters_max` into result JSONs written before the driver recorded it.

Why this exists: a run in which only SOME steps hit the pressure iteration cap has a MEAN below
PMAXIT and therefore looks converged, while its step time is part convergence and part cap — the
np=1536 packed rung averaged 122.2 with individual steps at 200. `plot_foxberry.py` rejects a run
on its MAX for that reason, and older JSONs carry only the mean.

The driver now records the true max over every step. Here we can only recover the SAMPLED max, from
the heartbeat lines the driver prints every NSTEPS/10 steps:

    [run] step 40/100  (200 pressure iters)

That is a lower bound on the true max, which is the safe direction: it can only fail to reject a
bad run, never reject a good one. The value written is flagged with `pressure_iters_max_source`
so it is never mistaken for the real thing.

Usage:  python backfill_iters_max.py [results/snellius-genoa ...]
"""
import glob
import json
import os
import re
import sys

STEP = re.compile(r"^\[run\] (?:step|warmup) \d+/\d+\s+(?:done \([\d.]+s, )?\((\d+) pressure iters",
                  re.M)
ALT = re.compile(r"^\[run\] .*?\((\d+) pressure iters", re.M)

dirs = sys.argv[1:] or ["results/snellius-genoa", "results/snellius-h100"]
n_done = n_skip = 0
for d in dirs:
    for jf in sorted(glob.glob(os.path.join(d, "fb_*.json"))):
        rec = json.load(open(jf))
        if "pressure_iters_max" in rec:
            n_skip += 1
            continue
        lf = jf[:-5] + ".log"
        if not os.path.exists(lf):
            print(f"  no log for {os.path.basename(jf)} — left alone (mean-only fallback applies)")
            continue
        txt = open(lf, errors="replace").read()
        vals = [int(v) for v in ALT.findall(txt)]
        if not vals:
            continue
        rec["pressure_iters_max"] = max(vals)
        rec["pressure_iters_max_source"] = "sampled from log heartbeats (lower bound)"
        json.dump(rec, open(jf, "w"), indent=1)
        n_done += 1
        flag = "  <-- CAPPED" if max(vals) >= rec["pmaxit"] else ""
        print(f"  {os.path.basename(jf)}: max {max(vals)} of {rec['pmaxit']}{flag}")
print(f"backfilled {n_done}, already had the field {n_skip}")
