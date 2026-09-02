#!/usr/bin/env python
"""Backfill `telescope` (and the predicted `hierarchy`) in result JSONs written by a driver that
recorded the TELESCOPE env flag rather than the solver's state. Since 2026-09-02 telescoping is
the solver DEFAULT, so a run with `telescope: 0` and no explicit TELESCOPE=0 (its signature: the
residual-stop era, `vres > 0`, and the telescoped iteration count) actually telescoped. The driver
now records `Solver.pressure_telescope()`; this script exists for the JSONs produced in between
(and after any re-sync from the cluster). Idempotent.

Usage: PYTHONPATH=<flow build> python backfill_telescope.py [results/snellius-genoa]
"""
import glob, json, os, sys
from peclet import flow

resdir = sys.argv[1] if len(sys.argv) > 1 else "results/snellius-genoa"
n = 0
for f in sorted(glob.glob(os.path.join(resdir, "fb_*.json"))):
    d = json.load(open(f))
    if int(d.get("telescope", 0)) != 0 or float(d.get("vres", 0)) <= 0:
        continue
    flow.set_decomposition_levels(int(d.get("decomp_levels", 7)))
    g = d["global"]
    d["telescope"] = 1
    d["hierarchy"] = [{"global": list(gg), "ranks": r, "block0": list(b), "ratio": list(q), "telescope": bool(t)}
                      for gg, r, b, q, t in flow.predict_hierarchy(g[0], g[1], g[2], d["np"], int(d.get("mglevels", 8)), True)]
    d["telescope_backfilled"] = "env flag recorded 0; solver default ON since 2026-09-02 (backfill_telescope.py)"
    json.dump(d, open(f, "w"), indent=1)
    n += 1
print(f"backfilled {n} file(s) in {resdir}")
