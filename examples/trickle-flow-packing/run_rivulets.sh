#!/usr/bin/env bash
# Kept as a file: the run is then one exec from any shell, and a supervisor that re-runs a
# long command line cannot re-enter it.
cd "$(dirname "$0")"
export PECLET_LOCAL_BUILD="/home/frankp/Codes/suite/flow/build_l3_cuda_final:/home/frankp/Codes/suite/dem/build_l4_cuda:/home/frankp/Codes/suite/core/python/build_geom"
export PATH=/usr/local/cuda-13.2/bin:$PATH
export OMP_NUM_THREADS=8 OMP_PROC_BIND=false PYTHONUNBUFFERED=1
exec /home/frankp/Codes/suite/.venv/bin/python render_trickle_rivulets.py \
     --nx 96 --nz 192 --tend 1500 --beta 0.30 --frames 250
