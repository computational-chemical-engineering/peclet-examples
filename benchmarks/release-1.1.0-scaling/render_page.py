#!/usr/bin/env python
"""Generate `index.qmd` from `index.qmd.in` by substituting the measured numbers.

Every figure the prose quotes comes from `headline.json`, which `analyze.py` computes from the raw
results. A sentence therefore cannot quote a number the data does not contain — which is the
failure mode that matters most in a record other people are asked to cite. An unresolved
placeholder is a hard error, not a silently rendered `{{...}}`.

    python analyze.py results && python render_page.py
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
src = (HERE / "index.qmd.in").read_text()
h = json.loads((HERE / "headline.json").read_text())

# A few values the template wants that are properties of the run protocol rather than of a ladder.
runs = [json.loads(p.read_text()) for p in (HERE / "results").rglob("*.json")]
runs = [r for r in runs if r.get("schema") == "peclet-scaling-1"]
if runs:
    h.setdefault("nsteps_timed", runs[0]["perf"]["nsteps"])
    h.setdefault("nwarmup", runs[0]["perf"]["warmup"])
    h.setdefault("gate_runs_steps", runs[0]["gate"]["steps"])
strong_gpu = sorted((r for r in runs if r["case"] == "bed" and r["mode"] == "strong"
                     and r["backend"] == "Cuda"), key=lambda r: r["ranks"])
if strong_gpu:
    h.setdefault("t_top_per_gpu_m", f"{strong_gpu[-1]['cells_per_rank'] / 1e6:.1f}")

out = src
for k, v in h.items():
    out = out.replace("{{" + k + "}}", str(v))

left = sorted(set(re.findall(r"\{\{(?!<)\s*([a-z0-9_]+)\s*\}\}", out)))
if left:
    sys.exit(f"FATAL: unresolved placeholders (not in headline.json): {left}\n"
             f"       run `python analyze.py results` first, or add them in analyze.headline()")

(HERE / "index.qmd").write_text(out)
print(f"wrote index.qmd ({len(h)} values substituted)")
