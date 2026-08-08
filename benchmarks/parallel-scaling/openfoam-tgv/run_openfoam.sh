#!/usr/bin/env bash
# Run the tiled-TGV OpenFOAM benchmark case (icoFoam, all-cyclic box) and emit a JSON result
# compatible with tgv_bench.py's output. Container: opencfd/openfoam-default:2412 (podman) by
# default; set FOAM_NATIVE=1 on systems with a module-provided OpenFOAM (e.g. Snellius).
#
# Usage: NP=4 NX=128 NY=128 NZ=128 NSTEPS=20 OUT=of_np4.json ./run_openfoam.sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
NP=${NP:-1}
NX=${NX:-64}; NY=${NY:-64}; NZ=${NZ:-64}
NSTEPS=${NSTEPS:-20}
TILE=${TILE:-64}                       # cells per 2*pi tile (matches peclet TILE=64)
OUT=${OUT:-of_np${NP}.json}
LABEL=${LABEL:-openfoam-v2412}
IMG=${IMG:-docker.io/opencfd/openfoam-default:2412}

# geometry: cell size 2*pi/TILE, box = N * cell size; dt at CFL 0.2 (U0=1), like the peclet runs
PI=3.141592653589793
DX=$(python3 -c "print(2*$PI/$TILE)")
LX=$(python3 -c "print($NX*2*$PI/$TILE)")
LY=$(python3 -c "print($NY*2*$PI/$TILE)")
LZ=$(python3 -c "print($NZ*2*$PI/$TILE)")
DT=$(python3 -c "print(0.2*2*$PI/$TILE)")
ENDT=$(python3 -c "print($NSTEPS*0.2*2*$PI/$TILE)")

WORK=$(mktemp -d "${TMPDIR:-/tmp}/oftgv.XXXXXX")
# On failure: dump the OpenFOAM logs BEFORE cleanup (otherwise the evidence is deleted)
trap 'code=$?; if [ $code -ne 0 ]; then
        echo "[run_openfoam FAILED exit=$code] last lines of each stage log:" >&2
        for f in "$WORK"/case/log.*; do
          [ -f "$f" ] && { echo "--- $f:" >&2; tail -8 "$f" >&2; }
        done
      fi; rm -rf "$WORK"' EXIT
cp -r "$HERE/case" "$WORK/case"
for f in system/blockMeshDict system/controlDict system/decomposeParDict; do
  sed -i -e "s/@NX@/$NX/g; s/@NY@/$NY/g; s/@NZ@/$NZ/g" \
         -e "s/@LX@/$LX/g; s/@LY@/$LY/g; s/@LZ@/$LZ/g" \
         -e "s/@DT@/$DT/g; s/@ENDT@/$ENDT/g; s/@NP@/$NP/g" \
         -e "s/@NTX@/$((NX / TILE))/g; s/@NTY@/$((NY / TILE))/g; s/@NTZ@/$((NZ / TILE))/g" \
         "$WORK/case/$f"
done

RUNLOG="$WORK/case/log.run"
if [ "${FOAM_NATIVE:-0}" = 1 ]; then
  cd "$WORK/case"
  blockMesh > log.blockMesh 2>&1
  setExprFields > log.setExprFields 2>&1
  if [ "$NP" -gt 1 ]; then
    decomposePar > log.decomposePar 2>&1
    mpirun -np "$NP" icoFoam -parallel > "$RUNLOG" 2>&1
  else
    icoFoam > "$RUNLOG" 2>&1
  fi
  cd "$HERE"
else
  # --user 0:0 -> container root == host user (rootless podman) so the mount is writable;
  # explicit cd because the image's login profile overrides -w with $HOME
  podman run --rm --user 0:0 -v "$WORK/case:/case:Z" "$IMG" bash -lc "
    cd /case &&
    blockMesh > log.blockMesh 2>&1 &&
    setExprFields > log.setExprFields 2>&1 &&
    if [ $NP -gt 1 ]; then
      decomposePar > log.decomposePar 2>&1 &&
      mpirun -np $NP --allow-run-as-root --bind-to core icoFoam -parallel > log.run 2>&1
    else
      icoFoam > log.run 2>&1
    fi"
fi

# per-step wall time: diff consecutive cumulative ExecutionTime stamps, average the last half
python3 - "$RUNLOG" "$NP" "$NX" "$NY" "$NZ" "$NSTEPS" "$LABEL" "$OUT" <<'EOF'
import json, re, sys
log, np_, nx, ny, nz, nsteps, label, out = sys.argv[1:]
np_, nx, ny, nz, nsteps = int(np_), int(nx), int(ny), int(nz), int(nsteps)
t = [float(m.group(1)) for m in re.finditer(r"ExecutionTime = ([0-9.eE+-]+) s", open(log).read())]
if len(t) < 4:
    sys.exit(f"too few ExecutionTime stamps in {log} ({len(t)}) - run failed?")
d = [b - a for a, b in zip(t, t[1:])]
d = d[len(d) // 2:]  # steady half
ms = 1e3 * sum(d) / len(d)
cells = nx * ny * nz
res = {"label": label, "np": np_, "backend": "cpu", "global": [nx, ny, nz], "cells": cells,
       "nsteps": nsteps, "ms_per_step": ms, "mcells_per_s": cells / (ms / 1e3) / 1e6,
       "code": "openfoam", "solver": "icoFoam+GAMG"}
json.dump(res, open(out, "w"), indent=1)
print(f"[result] {ms:.1f} ms/step  {res['mcells_per_s']:.2f} Mcell/s  -> {out}")
EOF
