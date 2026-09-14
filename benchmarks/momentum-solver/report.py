#!/usr/bin/env python3
"""Tabulate the pinned-momentum-solver ladders.

    python report.py [results]

One row per (rung, pin). Efficiency is against each ladder's OWN 24-core baseline, so the
two ladders are compared on wall time, not on an efficiency that each computes against a
different denominator. `it/cmpt` is momentum_sweeps/3: RB-GS sweeps, MG V-cycles, Chebyshev
iterations -- NOT comparable between solvers, only within one.
"""
import json
import statistics as st
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
rows = []
for f in sorted(root.rglob("*.json")):
    d = json.load(open(f))
    s = d["perf"]["steps"]
    med = lambda k: st.median([x[k] for x in s if k in x])
    rows.append(dict(
        pin=d["solver"].get("vmg_pin", "auto"), ranks=d["ranks"],
        tag=d.get("label", "").replace("snellius-genoa", "").lstrip("_") or "-",
        cpr=d["cells_per_rank"], step=d["perf"]["ms_per_step_median"],
        mom=med("momentum") * 1e3, proj=med("projection") * 1e3,
        it=med("momentum_sweeps") / 3 if any("momentum_sweeps" in x for x in s) else float("nan"),
        pit=d["perf"]["pressure_iters_mean"], gate=d["gate"]["value"]))

base = {(r["pin"], r["tag"]): r["step"] for r in rows if r["ranks"] == 24}
for pin, tag in sorted({(r["pin"], r["tag"]) for r in rows}):
    lad = sorted([r for r in rows if r["pin"] == pin and r["tag"] == tag],
                 key=lambda r: r["ranks"])
    if not lad:
        continue
    b = base.get((pin, tag))
    print(f"\n## momentum solver pinned to '{pin}'  [{tag}]\n")
    print("| cores | cells/rank | step ms | momentum | projection | it/cmpt | p-iters | "
          "speedup | eff. | <u> |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in lad:
        sp = b / r["step"] if b else float("nan")
        eff = sp / (r["ranks"] / 24.0) if b else float("nan")
        print(f"| {r['ranks']} | {r['cpr']:.0f} | {r['step']:.1f} | {r['mom']:.1f} | "
              f"{r['proj']:.1f} | {r['it']:.1f} | {r['pit']:.1f} | "
              f"{sp:.1f}x | {100 * eff:.0f} % | {r['gate']:.10e} |")

# head-to-head on wall time, which is the question the campaign exists to answer
rows_hh = [r for r in rows if r["tag"] in ("vmgoff", "vmgon", "cheb101")]
pins = sorted({r["pin"] for r in rows_hh})
if len(pins) > 1:
    print("\n## head-to-head (step ms; ratio against the slowest pin at that rung)\n")
    print("| cores | " + " | ".join(pins) + " | best |")
    print("|---:|" + "---:|" * len(pins) + "---|")
    for n in sorted({r["ranks"] for r in rows_hh}):
        cells = {p: next((r["step"] for r in rows_hh if r["ranks"] == n and r["pin"] == p), None)
                 for p in pins}
        have = {p: v for p, v in cells.items() if v}
        best = min(have, key=have.get) if have else "-"
        worst = max(have.values()) if have else 1.0
        print(f"| {n} | " + " | ".join(
            f"{cells[p]:.1f} ({worst / cells[p]:.2f}x)" if cells[p] else "-" for p in pins)
            + f" | **{best}** |")
