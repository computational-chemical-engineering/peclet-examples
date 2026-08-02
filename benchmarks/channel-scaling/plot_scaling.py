#!/usr/bin/env python
"""Weak-scaling figure for the Snellius channel-DNS runs (46M cells/GPU fixed)."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Measured on Snellius gpu_h100 (H100), 46M cells/GPU fixed, GPU-aware MPI halo.
# (from chan-weak-25094513.out; steady ms/step excludes 50-step warmup)
gpus   = np.array([1, 2, 4, 8])
ms     = np.array([1369.2, 1299.8, 1712.6, 2942.3])   # ms/step
mcells = np.array([33, 70, 106, 124])                 # Mcell-updates/s
nodes  = ["1 node", "1 node", "1 node", "2 nodes"]

eff = ms[0] / ms * 100.0   # weak-scaling efficiency (ideal = flat ms/step)

fig, ax = plt.subplots(1, 2, figsize=(11, 4.3))

a = ax[0]
a.plot(gpus, ms, "o-", color="C0", ms=7)
a.axhline(ms[0], color="grey", ls=":", lw=1, label="ideal (flat)")
for x, y, n in zip(gpus, ms, nodes):
    a.annotate(f"{y:.0f} ms\n{100*ms[0]/y:.0f}%", (x, y), textcoords="offset points",
               xytext=(0, 8), ha="center", fontsize=8)
a.set_xscale("log", base=2); a.set_xticks(gpus); a.set_xticklabels(gpus)
a.set_xlabel("H100 GPUs (46 M cells each)"); a.set_ylabel("ms / step (steady)")
a.set_title("Weak scaling — time per step"); a.legend(fontsize=8); a.set_ylim(0, 3200)
a.axvspan(4.5, 9, color="orange", alpha=0.08); a.text(6, 300, "multi-node", fontsize=8, color="C1", ha="center")

a = ax[1]
a.plot(gpus, mcells, "s-", color="C2", ms=7)
a.plot(gpus, mcells[0]*gpus, "k:", lw=1, label="ideal (linear)")
a.set_xscale("log", base=2); a.set_xticks(gpus); a.set_xticklabels(gpus)
a.set_xlabel("H100 GPUs"); a.set_ylabel("M cell-updates / s")
a.set_title("Weak scaling — throughput"); a.legend(fontsize=8)

plt.suptitle("Channel DNS weak scaling on Snellius (H100, GPU-aware MPI, 46 M cells/GPU, Δ⁺=1.5 cross-section)")
plt.tight_layout()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weak_scaling.png")
plt.savefig(out, dpi=110); print("wrote", out)
for g, m, e, mc in zip(gpus, ms, eff, mcells):
    print(f"  {g} GPU: {m:.0f} ms/step, {e:.0f}% weak-eff, {mc} Mcell/s")
