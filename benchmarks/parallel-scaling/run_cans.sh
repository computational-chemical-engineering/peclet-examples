#!/usr/bin/env bash
# Run the tiled-TGV CaNS benchmark (CaNS-World/CaNS, 2nd-order staggered FD, FFT Poisson,
# pencil decomposition) and emit a JSON result compatible with tgv_bench.py's output.
#
# Usage: NP=4 NX=128 NY=128 NZ=128 NSTEPS=20 OUT=cans_np4.json ./run_cans.sh
# CANS points at the built binary (default: ~/Codes/scaling-refs/CaNS/run/cans).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
NP=${NP:-1}
NX=${NX:-64}; NY=${NY:-64}; NZ=${NZ:-64}
NSTEPS=${NSTEPS:-20}
TILE=${TILE:-64}                    # cells per 2*pi tile, matching the peclet runs
OUT=${OUT:-cans_np${NP}.json}
case "$OUT" in /*) : ;; *) OUT="$PWD/$OUT" ;; esac   # resolve before we cd into the workdir
LABEL=${LABEL:-cans}
CANS=${CANS:-$HOME/Codes/scaling-refs/CaNS/run/cans}
MPIRUN=${MPIRUN:-/usr/bin/mpirun}
NTHREADS=${OMP_NUM_THREADS:-1}
# 2DECOMP pencil grid (fairness knob): "0,0" = library auto-factorization; explicit "P,Q"
# (P*Q = NP) can keep one FFT-transpose all-to-all intra-node — decisive across nodes.
DIMS=${DIMS:-0,0}
D1=${DIMS%,*}; D2=${DIMS#*,}

LX=$(python3 -c "import math; print($NX/$TILE*2*math.pi)")
LY=$(python3 -c "import math; print($NY/$TILE*2*math.pi)")
LZ=$(python3 -c "import math; print($NZ/$TILE*2*math.pi)")

WORK=$(mktemp -d "${TMPDIR:-/tmp}/canstgv.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/data"
cat > "$WORK/input.nml" <<EOF
&dns
ng(1:3) = $NX, $NY, $NZ
l(1:3) =  $LX, $LY, $LZ
gtype = 1, gr = 0.
cfl = 0.95, dtmax = 1.e5, dt_f = -1.
visci = 100.
inivel = 'tgv'
is_wallturb = F
nstep = $NSTEPS, time_max = 1e9, tw_max = 1e9
stop_type(1:3) = T, F, F
restart = F, is_overwrite_save = T, nsaves_max = 0
icheck = 10, iout0d = 1000000, iout1d = 1000000, iout2d = 1000000, iout3d = 1000000, isave = 1000000
cbcvel(0:1,1:3,1) = 'P','P',  'P','P',  'P','P'
cbcvel(0:1,1:3,2) = 'P','P',  'P','P',  'P','P'
cbcvel(0:1,1:3,3) = 'P','P',  'P','P',  'P','P'
cbcpre(0:1,1:3)   = 'P','P',  'P','P',  'P','P'
bcvel(0:1,1:3,1) =  0.,0.,   0.,0.,   0.,0.
bcvel(0:1,1:3,2) =  0.,0.,   0.,0.,   0.,0.
bcvel(0:1,1:3,3) =  0.,0.,   0.,0.,   0.,0.
bcpre(0:1,1:3)   =  0.,0.,   0.,0.,   0.,0.
bforce(1:3) = 0., 0., 0.
is_forced(1:3) = F, F, F
velf(1:3) = 0., 0., 0.
dims(1:2) = $D1, $D2, ipencil_axis = 1
/
&cudecomp
cudecomp_t_comm_backend = 0, cudecomp_is_t_enable_nccl = T, cudecomp_is_t_enable_nvshmem = T
cudecomp_h_comm_backend = 0, cudecomp_is_h_enable_nccl = T, cudecomp_is_h_enable_nvshmem = T
/
&numerics
is_impdiff = F, is_impdiff_1d = F
is_poisson_dtdma = F
/
&other_options
is_debug = F, is_timing = T
/
&io
io_backend = 'mpiio'
/
EOF

cd "$WORK"
# NPFLAG: '-np' for OpenMPI mpirun (default), '-n' for srun
$MPIRUN ${NPFLAG:--np} "$NP" ${MPIFLAGS:---bind-to core} "$CANS" input.nml > log.run 2>&1 || {
  tail -5 log.run >&2; exit 1; }

# per-step wall time: "Average, minimum & maximum elapsed time" line after each step; steady half
python3 - log.run "$NP" "$NX" "$NY" "$NZ" "$NSTEPS" "$LABEL" "$NTHREADS" "$OUT" "$DIMS" <<'EOF'
import json, re, sys
log, np_, nx, ny, nz, nsteps, label, nt, out, dims = sys.argv[1:]
np_, nx, ny, nz, nsteps = int(np_), int(nx), int(ny), int(nz), int(nsteps)
txt = open(log).read()
avg = [float(m.group(1)) for m in re.finditer(
    r"Average, minimum & maximum elapsed time:\s*\n\s*([0-9.E+-]+)", txt)]
avg = avg[:nsteps]  # drop the trailing end-of-run save timing
if len(avg) < 4:
    sys.exit(f"too few timing lines in {log} ({len(avg)})")
d = avg[len(avg) // 2:]
ms = 1e3 * sum(d) / len(d)
cells = nx * ny * nz
res = {"label": label, "np": np_, "backend": "cpu", "omp_threads": nt,
       "global": [nx, ny, nz], "cells": cells, "nsteps": nsteps, "ms_per_step": ms,
       "mcells_per_s": cells / (ms / 1e3) / 1e6, "code": "cans", "solver": "RK3+FFT",
       "dims": dims}
json.dump(res, open(out, "w"), indent=1)
print(f"[result] {ms:.1f} ms/step  {res['mcells_per_s']:.2f} Mcell/s  -> {out}")
EOF
