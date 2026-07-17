#!/bin/bash
# MUSEN GPU production runs + text exports (sequential).
set -u
BASE="/tmp/claude-1003/-home-frankp-Codes-suite/9e9b807a-7a8a-4948-a080-545a0f831797/scratchpad/dosta2024/SupplementaryMaterial/Scripts/MUSEN/cases"
CM=~/Codes/dem-bench/musen/build/CMUSEN

for case in penetration_050k penetration_100k silo_large_m1 silo_small_m1 mixer; do
  cd "$BASE/$case" || continue
  rm -f ${case}_res_gpu.mdem
  start=$(date +%s)
  $CM -s=${case}_gpu > musen_sim.log 2>&1
  ec=$?
  end=$(date +%s)
  echo "$case sim exit=$ec wall=$((end-start))s"
  cat > export_job <<EOF
NEW_JOB
COMPONENT              EXPORT_TO_TEXT
SOURCE_FILE            ${case}_res_gpu.mdem
RESULT_FILE            $PWD/${case}_export.txt
TEXT_EXPORT_OBJECTS    1 0 0
TEXT_EXPORT_CONST      1 0 1 0 0
TEXT_EXPORT_TD_PART    0 1 0 0 0 0 0 0 0
EOF
  $CM -s=export_job > musen_export.log 2>&1
  echo "$case export exit=$? size=$(stat -c%s ${case}_export.txt 2>/dev/null)"
done
echo "ALL MUSEN PRODUCTION DONE"
