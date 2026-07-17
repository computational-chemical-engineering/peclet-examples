#!/bin/bash
# peclet-dem production accuracy runs (sequential on GPU).
set -u
cd ~/Codes/dem-bench/peclet
PY=/home/frankp/Codes/suite/dem/.venv/bin/python
EXP=/home/frankp/Codes/dem-bench/dem-exp/build

echo "== case3 sym-PGS 50k/100k =="
for n in 50 100; do
  PECLET_DEM_SYMMETRIC_PGS=1 PYTHONPATH=$EXP $PY case3_impact.py --n $n \
    --out case3_${n}k_peclet_sympgs.npz 2>&1 | tail -2
done

echo "== case3 one-sided (as-is solver) 50k/100k =="
for n in 50 100; do
  PYTHONPATH=$EXP $PY case3_impact.py --n $n \
    --out case3_${n}k_peclet_onesided.npz 2>&1 | tail -2
done

echo "== case1 silo full 5 s: one-sided (as-is) =="
for o in large small; do
  for m in M1 M2; do
    PYTHONPATH=$EXP $PY case1_silo.py --orifice $o --mat $m --tend 5.0 \
      --out case1_${o}_${m}_onesided.npz 2>&1 | tail -1
  done
done

echo "== case1 silo full 5 s: symmetric PGS (large/M1 + small/M1) =="
for o in large small; do
  PECLET_DEM_SYMMETRIC_PGS=1 PYTHONPATH=$EXP $PY case1_silo.py --orifice $o --mat M1 \
    --tend 5.0 --out case1_${o}_M1_sympgs.npz 2>&1 | tail -1
done

echo "== case2 drum 5 s: both configs (approximated single pair material) =="
PYTHONPATH=$EXP $PY case2_mixer.py --out case2_peclet_onesided.npz 2>&1 | tail -2
PECLET_DEM_SYMMETRIC_PGS=1 PYTHONPATH=$EXP $PY case2_mixer.py \
  --out case2_peclet_sympgs.npz 2>&1 | tail -2

echo "ALL PECLET PRODUCTION DONE"
