#!/usr/bin/env python
"""Analysis for the peclet 1.0.0 scaling deposit: gates, tables, figures.

Reads every `results/**/*.json` written by `scaling_bench.py` and produces

  summary.md              the results tables the page and the report both include
  gates.md                the correctness gates, PASS/FAIL, with the numbers
  weak_scaling.png        W: per-GPU throughput and pressure iterations, 1 -> 32 H100
  strong_scaling.png      S and T: time per step against rank count, both machines
  phase_breakdown.png     where the step time goes, across the weak ladder

    python analyze.py [results_dir]

Nothing here interprets a run that failed its own gate: `scaling_bench.py` refuses to write a
result whose bed is not a converged packing, and a rung whose pressure solve hit its cap is
reported as such rather than plotted as a timing.
"""
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results")

# Validated categorical slots 1-3 (dataviz reference palette; all-pairs clean in both modes).
# The aqua slot sits below 3:1 on the light surface, so every figure that uses it is accompanied
# by the full table in summary.md — the relief the contrast rule requires.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#b8b7b2"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": MUTED, "grid.alpha": 0.35, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "legend.frameon": False, "figure.dpi": 150,
})


def load(root):
    runs = []
    for f in sorted(root.rglob("*.json")):
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            print(f"  ! unreadable: {f}")
            continue
        if d.get("schema") != "peclet-scaling-1":
            continue
        d["_file"] = f
        d["_machine"] = "h100" if "h100" in f.parent.name else "genoa"
        d["_tag"] = f.stem.split("_", 3)[3] if len(f.stem.split("_")) > 3 else ""
        runs.append(d)
    return runs


def pick(runs, case=None, mode=None, machine=None, tag=""):
    """Rungs of one ladder, one per rank count (untagged runs are the primary series)."""
    sel = [r for r in runs
           if (case is None or r["case"] == case)
           and (mode is None or r["mode"] == mode)
           and (machine is None or r["_machine"] == machine)
           and r["_tag"] == tag]
    by_n = {}
    for r in sel:
        by_n.setdefault(r["ranks"], r)
    return [by_n[n] for n in sorted(by_n)]


def ms(r):
    return r["perf"]["ms_per_step_median"]


def fmt(x, n=3):
    return "—" if x is None else f"{x:.{n}g}"


# ---------------------------------------------------------------- gates
def gates(runs):
    """Every run of the same problem must reproduce the same state after the same steps from rest.

    Runs are grouped by (case, resolution, step count): a run at a different grid spacing or a
    different number of steps is a DIFFERENT problem, and comparing it here would be meaningless
    rather than informative. A group of one is reported but cannot fail."""
    lines = ["# Correctness gates", ""]
    ok = True
    groups = {}
    for r in runs:
        if r.get("gate"):
            groups.setdefault((r["case"], round(r["spacing"], 12), r["gate"]["steps"]), []).append(r)

    for (case, h, steps), rs in sorted(groups.items()):
        rs.sort(key=lambda r: (r["ranks"], r["_file"].stem))
        vals = np.array([r["gate"]["value"] for r in rs])
        ref = vals[0]
        rel = np.abs(vals - ref) / abs(ref) if ref else np.abs(vals)
        q = rs[0]["gate"]["quantity"]
        lines += [f"## {case}: {q} after {steps} steps from rest, h = {h:g}", ""]
        lines += ["| run | ranks | machine | cells | value | rel. dev. |",
                  "|---|---:|---|---:|---:|---:|"]
        for r, v, d in zip(rs, vals, rel):
            lines.append(f"| {r['_file'].stem} | {r['ranks']} | {r['_machine']} | "
                         f"{r['cells_total'] / 1e6:.1f} M | {v:.12e} | {d:.2e} |")
        worst = float(rel.max()) if len(rel) else 0.0
        if len(rs) == 1:
            verdict, note = "SINGLE RUN", " — nothing to compare it against yet."
        else:
            verdict = "PASS" if worst < 1e-6 else ("MARGINAL" if worst < 1e-4 else "FAIL")
            note = (f" — worst relative deviation {worst:.2e} across {len(rs)} runs, "
                    f"{min(r['ranks'] for r in rs)} to {max(r['ranks'] for r in rs)} ranks, "
                    f"{len({r['_machine'] for r in rs})} machine(s).")
            ok = ok and verdict == "PASS"
        lines += ["", f"**{verdict}**{note}", ""]

    # the geometry is resampled independently on every rank of every rung
    bed = [r for r in runs if r["case"] == "bed"]
    if bed:
        dev = max(abs(r["phi_voxel"] - r["phi_packing"]) for r in bed)
        ok = ok and dev < 0.02
        lines += ["## Sampled solid fraction vs the packing", "",
                  f"Worst deviation {dev:.4f} over {len(bed)} runs "
                  f"(the driver refuses to run past 0.02). **{'PASS' if dev < 0.02 else 'FAIL'}**", ""]

    # a capped pressure solve reports the cap, not a converged step
    capped = [r for r in runs if r["perf"]["pressure_iters_max"] >= 200]
    ok = ok and not capped
    lines += ["## Pressure solve converged (never at its iteration cap)", "",
              (f"**FAIL** — capped rungs: {[r['_file'].stem for r in capped]}" if capped
               else f"**PASS** — worst iteration count "
                    f"{max(r['perf']['pressure_iters_max'] for r in runs)} against a cap of 200."),
              ""]

    # the weak ladder must give every rank the same block, or it is not a weak ladder
    weak = [r for r in runs if r["mode"] == "weak"]
    bad = [r["_file"].stem for r in weak if not r.get("blocks_uniform", True)]
    if weak:
        ok = ok and not bad
        lines += ["## Weak ladder: every rank owns an identical block", "",
                  (f"**FAIL** — non-uniform: {bad}" if bad else
                   f"**PASS** — uniform at all {len(weak)} weak rungs."), ""]
    return "\n".join(lines), ok


# ---------------------------------------------------------------- tables
def summary(runs):
    out = ["# Results", ""]
    for title, sel in (
        ("Weak scaling — H100, 384³ cells per GPU, cut-cell IBM",
         pick(runs, "bed", "weak", "h100")),
        ("Weak scaling — H100, Taylor–Green control (no geometry)",
         pick(runs, "tgv", "weak", "h100")),
        ("Strong scaling — H100, fixed 384³", pick(runs, "bed", "strong", "h100")),
        ("Strong scaling — genoa, fixed 384³", pick(runs, "bed", "strong", "genoa")),
        ("Strong scaling — genoa, Taylor–Green control", pick(runs, "tgv", "strong", "genoa")),
    ):
        if not sel:
            continue
        weak = sel[0]["mode"] == "weak"
        base = sel[0]
        out += [f"## {title}", "",
                "| " + ("GPUs" if sel[0]["_machine"] == "h100" else "cores")
                + " | cells | ms/step | Mcell/s | Mcell/s per rank | "
                + ("weak eff." if weak else "speedup / eff.")
                + " | pressure iters (mean/max) |",
                "|---:|---:|---:|---:|---:|---:|---:|"]
        for r in sel:
            per = r["perf"]["mcells_per_s_per_rank"]
            if weak:
                eff = f"{100 * per / base['perf']['mcells_per_s_per_rank']:.0f} %"
            else:
                sp = ms(base) / ms(r)
                eff = f"{sp:.1f}× / {100 * sp / (r['ranks'] / base['ranks']):.0f} %"
            out.append(
                f"| {r['ranks']} | {r['cells_total'] / 1e6:.1f} M | {ms(r):.1f} | "
                f"{r['perf']['mcells_per_s']:.1f} | {per:.2f} | {eff} | "
                f"{r['perf']['pressure_iters_mean']:.1f} / {r['perf']['pressure_iters_max']} |")
        out.append("")

    march = [r for r in runs if r.get("physics_result")]
    if march:
        out += ["## Permeability (marched to steady state)", "",
                "| run | ranks | cells | k/R² | steps | max&#124;div&#124; |",
                "|---|---:|---:|---:|---:|---:|"]
        for r in march:
            p = r["physics_result"]
            out.append(f"| {r['_file'].stem} | {r['ranks']} | {r['cells_total'] / 1e6:.1f} M | "
                       f"{p['k_over_R2']:.6e} | {p['march_steps']}"
                       f"{'' if p['march_converged'] else ' (CAP)'} | "
                       f"{p['max_open_divergence']:.2e} |")
        out.append("")

    spread = {}
    for r in runs:
        spread.setdefault((r["case"], r["mode"], r["_machine"], r["ranks"]), []).append(r)
    rep = {k: v for k, v in spread.items() if len(v) > 1}
    if rep:
        out += ["## Repeat allocations (run-to-run spread)", "",
                "| ladder | ranks | ms/step per allocation | spread |", "|---|---:|---|---:|"]
        for (case, mode, mach, n), v in sorted(rep.items()):
            t = [ms(x) for x in v]
            out.append(f"| {case} {mode} {mach} | {n} | {', '.join(f'{x:.1f}' for x in t)} | "
                       f"{max(t) / min(t):.2f}× |")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- figures
def log2_axis(ax, ns, label):
    ax.set_xscale("log", base=2)
    ax.set_xticks(ns)
    ax.set_xticklabels([str(n) for n in ns])
    ax.set_xlabel(label)


def fig_weak(runs, out):
    bed = pick(runs, "bed", "weak", "h100")
    tgv = pick(runs, "tgv", "weak", "h100")
    if not bed:
        return
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(5.4, 5.0), sharex=True,
                                 gridspec_kw={"height_ratios": [1.35, 1]})
    for sel, c, lab in ((bed, BLUE, "cut-cell IBM, sphere packing"),
                        (tgv, ORANGE, "Taylor–Green (no geometry)")):
        if not sel:
            continue
        n = [r["ranks"] for r in sel]
        a1.plot(n, [r["perf"]["mcells_per_s_per_rank"] for r in sel], "o-",
                color=c, lw=2, ms=7, label=lab)
        a2.plot(n, [r["perf"]["pressure_iters_mean"] for r in sel], "o-",
                color=c, lw=2, ms=7, label=lab)
    ns = [r["ranks"] for r in bed]
    a1.axhline(bed[0]["perf"]["mcells_per_s_per_rank"], color=MUTED, lw=1, ls="--", zorder=0)
    a1.annotate("ideal (single-GPU throughput)", (ns[0], bed[0]["perf"]["mcells_per_s_per_rank"]),
                textcoords="offset points", xytext=(4, 5), color=INK2, fontsize=8)
    eff = 100 * bed[-1]["perf"]["mcells_per_s_per_rank"] / bed[0]["perf"]["mcells_per_s_per_rank"]
    a1.annotate(f"{eff:.0f} % at {ns[-1]} GPUs\n{bed[-1]['cells_total'] / 1e9:.2f} Gcells",
                (ns[-1], bed[-1]["perf"]["mcells_per_s_per_rank"]),
                textcoords="offset points", xytext=(-8, -28), ha="right", color=INK, fontsize=8)
    a1.set_ylabel("throughput per GPU  [Mcell/s]")
    a1.set_ylim(bottom=0)
    a1.legend(loc="lower left")
    a2.set_ylabel("pressure iterations\nper step")
    a2.set_ylim(bottom=0)
    log2_axis(a2, ns, "H100 GPUs  (384³ cells each)")
    fig.suptitle("Weak scaling of peclet.flow 1.0.0 on Snellius H100", x=0.02, ha="left",
                 fontsize=10.5, y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out / "weak_scaling.png", bbox_inches="tight")
    plt.close(fig)


def fig_strong(runs, out):
    cpu = pick(runs, "bed", "strong", "genoa")
    gpu = pick(runs, "bed", "strong", "h100")
    if not (cpu or gpu):
        return
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4))
    for ax, sel, c, xl, mach in ((axes[0], cpu, ORANGE, "genoa cores", "genoa"),
                                 (axes[1], gpu, BLUE, "H100 GPUs", "h100")):
        if not sel:
            ax.set_visible(False)
            continue
        n = np.array([r["ranks"] for r in sel], float)
        t = np.array([ms(r) / 1e3 for r in sel])
        ax.loglog(n, t, "o-", color=c, lw=2, ms=7, label="peclet.flow 1.0.0")
        ax.loglog(n, t[0] * n[0] / n, ls="--", lw=1, color=MUTED, label="ideal")
        ax.set_xlabel(xl)
        ax.set_ylabel("wall time per step  [s]")
        ax.set_title(f"{sel[0]['cells_total'] / 1e6:.0f} M cells, fixed", fontsize=9, color=INK2,
                     loc="left")
        ax.legend(loc="lower left")
        e = (t[0] * n[0] / n[-1]) / t[-1]
        ax.annotate(f"{100 * e:.0f} % of ideal\nat {int(n[-1])}", (n[-1], t[-1]),
                    textcoords="offset points", xytext=(-6, 8), ha="right", fontsize=8, color=INK)
    fig.suptitle("Strong scaling, one fixed problem — cut-cell IBM through a sphere packing",
                 x=0.02, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out / "strong_scaling.png", bbox_inches="tight")
    plt.close(fig)


def fig_phases(runs, out):
    sel = pick(runs, "bed", "weak", "h100")
    if not sel or "predictor" not in sel[0]["perf"]["steps"][0]:
        return
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    n = [r["ranks"] for r in sel]
    x = np.arange(len(sel))
    parts = ("predictor", "momentum", "projection")
    bottom = np.zeros(len(sel))
    for key, c in zip(parts, (BLUE, ORANGE, AQUA)):
        v = np.array([1e3 * float(np.median([s[key] for s in r["perf"]["steps"]])) for r in sel])
        ax.bar(x, v, 0.62, bottom=bottom, color=c, label=key,
               edgecolor=SURFACE, linewidth=2)      # 2px surface gap between segments
        for xi, vi, bi in zip(x, v, bottom):
            if vi > 0.06 * (bottom + v).max():
                ax.text(xi, bi + vi / 2, f"{vi:.0f}", ha="center", va="center",
                        color=SURFACE, fontsize=7.5)
        bottom += v
    tot = np.array([ms(r) for r in sel])
    ax.plot(x, tot, "o", color=INK, ms=5, label="total step")
    ax.set_xticks(x)
    ax.set_xticklabels([str(v) for v in n])
    ax.set_xlabel("H100 GPUs  (384³ cells each)")
    ax.set_ylabel("time per step  [ms]")
    ax.legend(loc="upper left", ncol=2)
    ax.set_title("Where the step goes, across the weak ladder", fontsize=10.5, loc="left",
                 color=INK)
    fig.tight_layout()
    fig.savefig(out / "phase_breakdown.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- headline numbers
def headline(runs):
    """Every number the prose quotes, computed from the data.

    The page is generated from `index.qmd.in` with these substituted, so a sentence can never
    quote a figure the results do not contain — the failure mode that matters most in a record
    other people are asked to cite."""
    h = {}

    def ladder(key, sel):
        if not sel:
            return
        b, t = sel[0], sel[-1]
        h[f"{key}_base_n"] = b["ranks"]
        h[f"{key}_top_n"] = t["ranks"]
        h[f"{key}_base_ms"] = f"{ms(b):.0f}"
        h[f"{key}_top_ms"] = f"{ms(t):.0f}"
        h[f"{key}_top_s"] = f"{ms(t) / 1e3:.2f}"
        h[f"{key}_base_s"] = f"{ms(b) / 1e3:.1f}"
        h[f"{key}_top_gcells"] = f"{t['cells_total'] / 1e9:.2f}"
        h[f"{key}_top_mcells"] = f"{t['cells_total'] / 1e6:.0f}"
        h[f"{key}_base_per"] = f"{b['perf']['mcells_per_s_per_rank']:.3g}"
        h[f"{key}_top_per"] = f"{t['perf']['mcells_per_s_per_rank']:.3g}"
        h[f"{key}_base_iters"] = f"{b['perf']['pressure_iters_mean']:.1f}"
        h[f"{key}_top_iters"] = f"{t['perf']['pressure_iters_mean']:.1f}"
        h[f"{key}_top_throughput"] = f"{t['perf']['mcells_per_s']:.0f}"
        eff = t["perf"]["mcells_per_s_per_rank"] / b["perf"]["mcells_per_s_per_rank"]
        h[f"{key}_weak_eff"] = f"{100 * eff:.0f}"
        sp = ms(b) / ms(t)
        h[f"{key}_speedup"] = f"{sp:.1f}"
        h[f"{key}_strong_eff"] = f"{100 * sp / (t['ranks'] / b['ranks']):.0f}"

    wb = pick(runs, "bed", "weak", "h100")
    ladder("w", wb)
    ladder("wt", pick(runs, "tgv", "weak", "h100"))
    ladder("t", pick(runs, "bed", "strong", "h100"))
    ladder("s", pick(runs, "bed", "strong", "genoa"))
    ladder("st", pick(runs, "tgv", "strong", "genoa"))

    # what one H100 is worth, on this workload, measured on the same case at both ends
    g1 = pick(runs, "bed", "weak", "h100")
    c = pick(runs, "bed", "strong", "genoa")
    if g1 and c:
        per_core = c[-1]["perf"]["mcells_per_s"] / c[-1]["ranks"]
        h["cores_per_gpu"] = f"{g1[0]['perf']['mcells_per_s'] / per_core:.0f}"
        h["cpu_top_n"] = c[-1]["ranks"]

    # the cross-rung / cross-machine equivalence gate
    grp = [r for r in runs if r["case"] == "bed" and r.get("gate")
           and abs(r["spacing"] - (wb[0]["spacing"] if wb else 0)) < 1e-12]
    if grp:
        vals = np.array([r["gate"]["value"] for r in grp])
        rel = np.abs(vals - vals[0]) / abs(vals[0])
        h["gate_value"] = f"{vals[0]:.12e}"
        h["gate_digits"] = f"{vals[0]:.10e}"
        h["gate_worst"] = f"{rel.max():.0e}".replace("e-", "e−")
        h["gate_runs"] = len(grp)
        h["gate_max_ranks"] = max(r["ranks"] for r in grp)
        h["gate_max_div"] = f"{max(r['gate']['max_open_divergence'] for r in grp):.0e}"

    march = [r for r in runs if r.get("physics_result")]
    if march:
        ks = [r["physics_result"]["k_over_R2"] for r in march]
        h["k_over_R2"] = f"{ks[0]:.6f}"
        h["k_runs"] = len(ks)
        h["k_spread"] = (f"{max(abs(k / ks[0] - 1) for k in ks):.0e}".replace("e-", "e−")
                         if len(ks) > 1 else "—")
        h["k_march_steps"] = march[0]["physics_result"]["march_steps"]

    # what the geometry costs: same grid, same machine, with and without the immersed boundary
    wt = pick(runs, "tgv", "weak", "h100")
    if wb and wt:
        h["ibm_cost"] = f"{ms(wb[0]) / ms(wt[0]):.1f}"
        h["ibm_iters_ratio"] = (f"{wb[0]['perf']['pressure_iters_mean'] / max(wt[0]['perf']['pressure_iters_mean'], 1e-9):.1f}")

    if wb:
        h["cells_per_gpu_m"] = f"{wb[0]['cells_total'] / 1e6:.1f}"
        h["r_cells"] = f"{wb[0]['r_cells']:.0f}"
        h["phi"] = f"{wb[0]['phi_packing']:.2f}"
        h["levels"] = len(wb[0]["solver"]["level_ratios"])
        h["flow_version"] = wb[0]["flow_version"]
    return h


def main():
    runs = load(ROOT)
    if not runs:
        sys.exit(f"no results under {ROOT}")
    print(f"loaded {len(runs)} runs from {ROOT}")
    here = pathlib.Path(__file__).parent
    g, ok = gates(runs)
    (here / "gates.md").write_text(g + "\n")
    (here / "summary.md").write_text(summary(runs) + "\n")
    hl = headline(runs)
    (here / "headline.json").write_text(json.dumps(hl, indent=1, sort_keys=True) + "\n")
    fig_weak(runs, here)
    fig_strong(runs, here)
    fig_phases(runs, here)
    print(f"wrote headline.json ({len(hl)} values), gates.md, summary.md, weak_scaling.png, strong_scaling.png, phase_breakdown.png")
    print("GATES:", "all pass" if ok else "SEE gates.md — something did not pass")


if __name__ == "__main__":
    main()
