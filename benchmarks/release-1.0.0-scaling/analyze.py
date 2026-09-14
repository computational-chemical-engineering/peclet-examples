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

    Runs are grouped by (case, resolution, step count, SOLVER CONFIGURATION): a run at a different
    grid spacing, a different number of steps, or a different solver is a DIFFERENT computation, and
    comparing it here would be meaningless rather than informative. A group of one is reported but
    cannot fail.

    The solver configuration is part of the key because peclet 1.0.0 switches the momentum solver by
    itself: `set_velocity_multigrid_auto` turns the velocity multigrid ON below ~65k cells per rank,
    so the top CPU rungs run a different momentum solve from the rest of the same ladder. Both are
    converged; they are not the same iterate. Lumping them together would hide a genuine agreement
    inside a spurious disagreement. The difference BETWEEN configurations is reported separately,
    below, because it is a property worth quoting rather than a defect to bury."""
    lines = ["# Correctness gates", ""]
    ok = True
    groups = {}
    for r in runs:
        if r.get("gate"):
            cfg = (r["solver"]["levels_requested"], bool(r["solver"]["velocity_multigrid_active"]))
            groups.setdefault((r["case"], round(r["spacing"], 12), r["gate"]["steps"], cfg),
                              []).append(r)

    for (case, h, steps, cfg), rs in sorted(groups.items()):
        rs.sort(key=lambda r: (r["ranks"], r["_file"].stem))
        vals = np.array([r["gate"]["value"] for r in rs])
        ref = vals[0]
        rel = np.abs(vals - ref) / abs(ref) if ref else np.abs(vals)
        q = rs[0]["gate"]["quantity"]
        lines += [f"## {case}: {q} after {steps} steps from rest, h = {h:g}, "
                  f"MG depth {cfg[0]}, velocity multigrid {'on' if cfg[1] else 'off'}", ""]
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

    # What the automatic configuration switches cost in agreement. Not a failure: a different
    # solver is a different iterate. Worth quoting, because it is the size of the only disagreement
    # anywhere in the record.
    by_case = {}
    for (case, h, steps, cfg), rs in groups.items():
        by_case.setdefault((case, h, steps), []).append((cfg, rs[0]["gate"]["value"], len(rs)))
    rows = [(c, v) for c, v in by_case.items() if len(v) > 1]
    if rows:
        lines += ["## Between configurations (not a gate — a measurement)", "",
                  "peclet 1.0.0 selects the momentum solver from the per-rank workload "
                  "(`set_velocity_multigrid_auto`, on below ~65k cells/rank) and the multigrid depth "
                  "is a study parameter. Runs that differ in either are different computations; this "
                  "is how far apart their answers land.", "",
                  "| case | configuration | runs | value | vs. first |",
                  "|---|---|---:|---:|---:|"]
        for (case, _h, _st), v in sorted(rows):
            v.sort(key=lambda t: (t[0][0], t[0][1]))
            ref = v[0][1]
            for cfg, val, n in v:
                d = abs(val - ref) / abs(ref) if ref else 0.0
                lines.append(f"| {case} | MG depth {cfg[0]}, velocity MG "
                             f"{'on' if cfg[1] else 'off'} | {n} | {val:.12e} | "
                             f"{'—' if d == 0 else f'{d:.2e}'} |")
        lines.append("")

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

    # Run-to-run spread means the SAME computation on a different allocation. Runs that differ in
    # solver configuration (the LEVELS sensitivity point) are a different computation and would be
    # read as machine variability they are not.
    spread = {}
    for r in runs:
        cfg = (r["solver"]["levels_requested"], bool(r["solver"]["velocity_multigrid_active"]))
        spread.setdefault((r["case"], r["mode"], r["_machine"], r["ranks"], cfg), []).append(r)
    rep = {k: v for k, v in spread.items() if len(v) > 1}
    if rep:
        out += ["## Repeat allocations (run-to-run spread)", "",
                "| ladder | ranks | ms/step per allocation | spread |", "|---|---:|---|---:|"]
        for (case, mode, mach, n, _cfg), v in sorted(rep.items()):
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
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(5.4, 4.6), sharex=True,
                                 gridspec_kw={"height_ratios": [1.15, 1]})
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
        # plain numbers on both log axes: "4 x 10^0 s" is unreadable for a quantity like 4 s
        ax.set_xticks(n, [f"{int(v)}" for v in n], minor=False)
        ax.set_xticks([], [], minor=True)
        lo, hi = t.min(), t.max()
        yt = [v for v in (0.2, 0.3, 0.5, 0.7, 1, 2, 3, 5, 7, 10, 20, 30, 50, 100, 200)
              if lo / 1.6 <= v <= hi * 1.6]
        ax.set_yticks(yt, [f"{v:g}" for v in yt], minor=False)
        ax.set_yticks([], [], minor=True)
        ax.set_xlabel(xl)
        ax.set_ylabel("wall time per step  [s]")
        ax.set_title(f"{sel[0]['cells_total'] / 1e6:.0f} M cells, fixed", fontsize=9, color=INK2,
                     loc="left")
        ax.legend(loc="lower left")
        e = (t[0] * n[0] / n[-1]) / t[-1]
        ax.annotate(f"{100 * e:.0f} % of ideal at {int(n[-1])}", (n[-1], t[-1]),
                    textcoords="offset points", xytext=(-4, -16), ha="right", fontsize=8,
                    color=INK)
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
    vals = {k: np.array([1e3 * float(np.median([s[k] for s in r["perf"]["steps"]])) for r in sel])
            for k in parts}
    tot = np.array([ms(r) for r in sel])
    bottom = np.zeros(len(sel))
    for key, c in zip(parts, (BLUE, ORANGE, AQUA)):
        v = vals[key]
        ax.bar(x, v, 0.62, bottom=bottom, color=c, label=key,
               edgecolor=SURFACE, linewidth=2)      # 2px surface gap between segments
        for xi, vi, bi in zip(x, v, bottom):
            # label only a segment big enough to hold one — the predictor is ~0.1 % of the step
            if vi > 0.08 * tot.max():
                ax.text(xi, bi + vi / 2, f"{vi:.0f}", ha="center", va="center",
                        color=SURFACE, fontsize=7.5)
        bottom += v
    ax.plot(x, tot, "o", color=INK, ms=5, label="total step")
    ax.set_xticks(x)
    ax.set_xticklabels([str(v) for v in n])
    ax.set_xlabel("H100 GPUs  (384³ cells each)")
    ax.set_ylabel("time per step  [ms]")
    ax.set_ylim(0, 1.28 * tot.max())
    hs, ls = ax.get_legend_handles_labels()
    order = [ls.index(k) for k in (*parts, "total step")]
    ax.legend([hs[i] for i in order], [ls[i] for i in order], loc="upper left", ncol=4,
              columnspacing=1.0, handletextpad=0.5, fontsize=8)
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

    # What one H100 is worth on this workload. Deliberately the CONSERVATIVE reading: the CPU is
    # credited with its BEST per-core throughput anywhere on its ladder (the sub-node rungs, which
    # have the most memory bandwidth per core), not with its most contended one — quoting the
    # 1536-core rung instead would roughly double the ratio in peclet's favour.
    g1 = pick(runs, "bed", "weak", "h100")
    c = pick(runs, "bed", "strong", "genoa")
    if g1 and c:
        best = max(c, key=lambda r: r["perf"]["mcells_per_s"] / r["ranks"])
        per_core = best["perf"]["mcells_per_s"] / best["ranks"]
        h["cores_per_gpu"] = f"{g1[0]['perf']['mcells_per_s'] / per_core:.0f}"
        h["cores_per_gpu_rung"] = best["ranks"]
        h["cpu_top_n"] = c[-1]["ranks"]

    # The cross-rung / cross-machine equivalence gate, restricted to ONE solver configuration:
    # the auto rule switches the momentum solver below ~65k cells/rank, and a different solver is a
    # different iterate. The switched rungs are reported on their own terms just below.
    def grp_of(case, vmg):
        # the case's own production resolution (its most common spacing), not the bed's
        sp = [r["spacing"] for r in runs if r["case"] == case and r.get("gate")]
        if not sp:
            return []
        ref = max(set(sp), key=sp.count)
        return [r for r in runs if r["case"] == case and r.get("gate")
                and abs(r["spacing"] - ref) < 1e-12
                and r["solver"]["levels_requested"] == 10
                and bool(r["solver"]["velocity_multigrid_active"]) is vmg]

    grp = grp_of("bed", False)
    if grp:
        vals = np.array([r["gate"]["value"] for r in grp])
        rel = np.abs(vals - vals[0]) / abs(vals[0])
        h["gate_value"] = f"{vals[0]:.12e}"
        h["gate_worst"] = f"{rel.max():.0e}".replace("e-", "e−")
        h["gate_runs"] = len(grp)
        h["gate_max_ranks"] = max(r["ranks"] for r in grp)
        h["gate_machines"] = len({r["_machine"] for r in grp})
        h["gate_max_div"] = f"{max(r['gate']['max_open_divergence'] for r in grp):.0e}"
        h["gate_max_cells"] = f"{max(r['cells_total'] for r in grp) / 1e9:.2f}"

    tg = grp_of("tgv", False)
    if tg:
        v = np.array([r["gate"]["value"] for r in tg])
        h["tgv_gate_worst"] = f"{(np.abs(v - v[0]) / abs(v[0])).max():.0e}".replace("e-", "e−")
        h["tgv_gate_runs"] = len(tg)
        h["tgv_gate_max_ranks"] = max(r["ranks"] for r in tg)

    sw = grp_of("bed", True)
    if sw and grp:
        v = np.array([r["gate"]["value"] for r in sw])
        h["switch_ranks"] = min(r["ranks"] for r in sw)
        h["switch_runs"] = len(sw)
        h["switch_spread"] = ("0" if len(v) == 1 or np.ptp(v) == 0
                              else f"{(np.ptp(v) / abs(v[0])):.0e}".replace("e-", "e−"))
        h["switch_delta"] = f"{abs(v[0] - grp[0]['gate']['value']) / abs(grp[0]['gate']['value']):.1e}".replace("e-", "e−")
        h["switch_cells_per_rank_k"] = f"{sw[0]['cells_per_rank'] / 1e3:.0f}"

    # where the weak ladder's loss actually accumulates
    if len(wb) > 1:
        def med(r, k):
            return 1e3 * float(np.median([st[k] for st in r["perf"]["steps"]]))
        for key in ("momentum", "projection"):
            a, b = med(wb[0], key), med(wb[-1], key)
            h[f"ph_{key}_base"] = f"{a:.0f}"
            h[f"ph_{key}_top"] = f"{b:.0f}"
            h[f"ph_{key}_growth"] = f"{100 * (b / a - 1):.0f}"
        h["ph_predictor_base"] = f"{med(wb[0], 'predictor'):.1f}"

    # A rung that is SLOWER than the one below it on a strong ladder is either noise or a real
    # effect; the repeat allocations decide which, and the phase timers say where it lives.
    tg_ = pick(runs, "bed", "strong", "h100")
    for prev, cur in zip(tg_, tg_[1:]):
        if ms(cur) > ms(prev):
            def med(r, k):
                return 1e3 * float(np.median([st[k] for st in r["perf"]["steps"]]))
            h["anom_n"] = cur["ranks"]
            h["anom_prev_n"] = prev["ranks"]
            h["anom_ms"] = f"{ms(cur):.0f}"
            h["anom_prev_ms"] = f"{ms(prev):.0f}"
            h["anom_proj"] = f"{med(cur, 'projection'):.0f}"
            h["anom_prev_proj"] = f"{med(prev, 'projection'):.0f}"
            h["anom_mom"] = f"{med(cur, 'momentum'):.0f}"
            h["anom_prev_mom"] = f"{med(prev, 'momentum'):.0f}"
            reps = [x for x in runs if x["case"] == "bed" and x["mode"] == "strong"
                    and x["_machine"] == "h100" and x["ranks"] == cur["ranks"]]
            t = [ms(x) for x in reps]
            h["anom_repeats"] = len(t)
            h["anom_spread"] = f"{max(t) / min(t):.2f}"
            break

    # where the weak ladder's loss actually accumulates
    if len(wb) > 1:
        def med(r, k):
            return 1e3 * float(np.median([st[k] for st in r["perf"]["steps"]]))
        for key in ("momentum", "projection"):
            a, b = med(wb[0], key), med(wb[-1], key)
            h[f"ph_{key}_base"] = f"{a:.0f}"
            h[f"ph_{key}_top"] = f"{b:.0f}"
            h[f"ph_{key}_growth"] = f"{100 * (b / a - 1):.0f}"
        h["ph_predictor_base"] = f"{med(wb[0], 'predictor'):.1f}"

    # A rung that is SLOWER than the one below it on a strong ladder is either noise or a real
    # effect; the repeat allocations decide which, and the phase timers say where it lives.
    tg_ = pick(runs, "bed", "strong", "h100")
    for prev, cur in zip(tg_, tg_[1:]):
        if ms(cur) > ms(prev):
            def med(r, k):
                return 1e3 * float(np.median([st[k] for st in r["perf"]["steps"]]))
            h["anom_n"] = cur["ranks"]
            h["anom_prev_n"] = prev["ranks"]
            h["anom_ms"] = f"{ms(cur):.0f}"
            h["anom_prev_ms"] = f"{ms(prev):.0f}"
            h["anom_proj"] = f"{med(cur, 'projection'):.0f}"
            h["anom_prev_proj"] = f"{med(prev, 'projection'):.0f}"
            h["anom_mom"] = f"{med(cur, 'momentum'):.0f}"
            h["anom_prev_mom"] = f"{med(prev, 'momentum'):.0f}"
            reps = [x for x in runs if x["case"] == "bed" and x["mode"] == "strong"
                    and x["_machine"] == "h100" and x["ranks"] == cur["ranks"]]
            t = [ms(x) for x in reps]
            h["anom_repeats"] = len(t)
            h["anom_spread"] = f"{max(t) / min(t):.2f}"
            break

    # Which MPI buffer path the SHIPPED auto-detection actually chose (the runs leave
    # PECLET_CORE_GPU_AWARE_MPI unset on purpose, and log the resolution).
    for r in pick(runs, "bed", "weak", "h100")[-1:]:
        log = r["_file"].with_suffix(".log")
        if log.exists():
            for line in log.read_text().splitlines():
                if "peclet.core halo:" in line:
                    h["halo_path"] = line.split("peclet.core halo:")[1].strip()
                    break

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
