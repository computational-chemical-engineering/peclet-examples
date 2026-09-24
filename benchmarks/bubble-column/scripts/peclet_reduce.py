#!/usr/bin/env python3
"""Reduce the peclet bubble-column run (run_peclet.py's checkpoint series) to the same observables
tbf_read.py writes for TBFsolver, so the page compares like with like.

    python peclet_reduce.py <run dir> [--out ../data/peclet_closed.npz] [--log <run.log>]

Reads the `series` JSON carried in <run dir>/ckpt.npz (one record per DT_OUT, written by
run_peclet.sample) — so it works on a run in progress — and, if given, the run log for the cost
(ms/step) and the time-step history.
"""
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case  # noqa: E402


def main():
    run = sys.argv[1]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "peclet_closed.npz")
    log = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else None
    z = np.load(os.path.join(run, "ckpt.npz"))
    series = json.loads(str(z["series"]))
    t = np.array([r["t"] for r in series])
    d = {
        "t": t,
        "rise_speed": np.array([r["drift"] for r in series]),
        "gas_volume": np.array([r["gas_volume"] for r in series]),
        "u_mix": np.array([r["u_mix"] for r in series]),
        "u_liq": np.array([r["u_liq"] for r in series]),
        "u_gas": np.array([r["u_gas"] for r in series]),
        "alpha_y": np.array([r["alpha_y"] for r in series]),
        "u_liq_y": np.array([r["ul_y"] for r in series]),
        "bubble_vol": np.array([r["bubble_vol"] for r in series]),
        "bubble_y": np.array([r["bubble_y"] for r in series]),
        "bubble_ux": np.array([r["bubble_ux"] for r in series]),
        "area": np.array([r["area"] for r in series]),
        "y": (np.arange(case.NY) + 0.5) * case.H,
        "grid": np.array([case.NX, case.NY, case.NZ]),
        "step": np.int64(z["step"]),
    }
    # marker volumes are exact per marker; the UNION gas volume dips while two markers overlap
    d["marker_volume_total"] = d["bubble_vol"].sum(axis=1)
    if log and os.path.exists(log):
        ms, dts = [], []
        for line in open(log):
            m = re.search(r"dt ([0-9.e+-]+) .* (\d+) ms/step", line)
            if m:
                dts.append(float(m.group(1)))
                ms.append(float(m.group(2)))
        d["log_dt"] = np.array(dts)
        d["log_ms_per_step"] = np.array(ms)
    np.savez(out, **d)
    v = d["marker_volume_total"]
    print(f"wrote {out}: {len(t)} records, t {t[0]:.2f} .. {t[-1]:.2f}, step {int(z['step'])}; "
          f"marker volume {v[0]:.9f} -> {v[-1]:.9f} (rel {v[-1]/v[0]-1:+.2e})")


if __name__ == "__main__":
    main()
