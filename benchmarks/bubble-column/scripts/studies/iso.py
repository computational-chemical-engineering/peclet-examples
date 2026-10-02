#!/usr/bin/env python3
"""Isolated-bubble variant of the bubble-column case: patch case.py's geometry and bubble list,
then hand over to the committed scripts unchanged.

    python iso.py peclet  --out DIR --t-end 40          # run_peclet.main()
    python iso.py tbfcase --out DIR --tf 40 --px 4 --pz 2 --no-averages   # make_tbf_case.main()
    python iso.py tbfread RUN --out X.npz                # tbf_read.main()
Box ISO_L (x, vertical periodic) x ISO_LY (y, walls) x ISO_L (z, periodic), in D; one bubble at the centre.
"""
import os
import sys

import numpy as np

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, SCRIPTS)
import case  # noqa: E402

L = float(os.environ.get("ISO_L", "4"))
LY = float(os.environ.get("ISO_LY", str(L)))
LX = float(os.environ.get("ISO_LX", str(L)))
case.LX, case.LY, case.LZ = LX, LY, L
S = case.CELLS_PER_D
case.NX, case.NY, case.NZ = int(LX * S), int(LY * S), int(L * S)
case.NBX = case.NBY = case.NBZ = 1
case.NB = 1
case.bubble_centres = lambda: np.array([[LX / 2, LY / 2, L / 2]])
case.VOID_FRACTION = np.pi / 6 / (LX * LY * L)

which = sys.argv.pop(1)
if which == "peclet":
    import run_peclet
    run_peclet.main()
elif which == "tbfcase":
    import make_tbf_case
    make_tbf_case.main()
elif which == "tbfread":
    import tbf_read
    tbf_read.main()
else:
    raise SystemExit(which)
