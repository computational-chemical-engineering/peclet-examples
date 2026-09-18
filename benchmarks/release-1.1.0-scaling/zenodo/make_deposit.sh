#!/bin/bash
# ==========================================================================================
# Build the Zenodo deposit for the peclet 1.1.0 scaling benchmark, and (only when asked)
# upload it as a DRAFT.
#
#   ./zenodo/make_deposit.sh                 # package locally: tarball + report + manifest
#   ZENODO_TOKEN=... ./zenodo/make_deposit.sh --upload    # + create a DRAFT deposition
#
# It NEVER publishes. Publishing mints a DOI and is irreversible, so the last step is a click
# in the Zenodo web form after a human has looked at the draft.
#
# Why a manual deposit rather than Zenodo's GitHub-release hook: the hook archives the WHOLE
# peclet-examples gallery at a tag and would mint a DOI for "the gallery". This record is one
# benchmark, and it has to be readable without GitHub — hence the self-contained tarball plus a
# standalone report.
# ==========================================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
BENCH="$PWD"
NAME="peclet-flow-1.1.0-scaling"
OUT="$BENCH/zenodo/build"
rm -rf "$OUT"; mkdir -p "$OUT"

command -v pandoc >/dev/null || { echo "FATAL: pandoc is needed to render the report"; exit 1; }
[ -f "$BENCH/summary.md" ] || { echo "FATAL: run 'python analyze.py results' first"; exit 1; }
[ -f "$BENCH/index.qmd" ]  || { echo "FATAL: run 'python render_page.py' first"; exit 1; }

# --- 1. the standalone report: ONE source (index.qmd), rendered self-contained --------------
echo "== rendering the report"
python3 "$BENCH/make_report.py" "$OUT"

# --- 2. the artifact: everything needed to redo the measurement -----------------------------
echo "== packaging $NAME.tar.gz"
COMMIT=$(git -C "$BENCH" rev-parse HEAD)
# The companion pinned-momentum-solver campaign goes in too. The 2026-09-15 addendum quotes its
# numbers, and analyze.py reads them from the SIBLING directory -- so a record that shipped without
# it could not reproduce its own corrections, which is exactly the failure this deposit is built to
# avoid. Both directories extract as siblings, so the relative path still resolves.
ADDENDUM=momentum-solver
tar --exclude='__pycache__' --exclude='zenodo/build' --exclude='.quarto' \
    --exclude='*.tar.gz' --exclude='logs' -czf "$OUT/$NAME.tar.gz" \
    -C "$(dirname "$BENCH")" "$(basename "$BENCH")" \
    $([ -d "$(dirname "$BENCH")/$ADDENDUM" ] && echo "$ADDENDUM")

# --- 3. provenance: what produced these numbers ---------------------------------------------
{
  echo "peclet.flow 1.1.0 scaling benchmark — provenance"
  echo
  echo "packaged          : $(date -Is)"
  echo "peclet-examples   : $COMMIT"
  echo "software          : peclet.flow 1.1.0 (tag v1.1.0, umbrella 24b0417)"
  echo "                    with peclet-core 1.0.2 (v1.0.2) and peclet-morton 1.0.1 (v1.0.1)"
  echo "                    -- the exact pins are in census-*.txt, taken from the build itself"
  echo "                    concept DOI 10.5281/zenodo.21132445"
  echo "machine           : Snellius (SURF), partitions gpu_h100 and genoa"
  echo
  echo "Build censuses (toolchain, MPI, driver, wheel sha256) are in census-*.txt."
  echo "Raw results are results/snellius-{h100,genoa}/*.json with their *.log beside them."
} > "$OUT/PROVENANCE.txt"
for c in "$BENCH"/census-*.txt; do [ -f "$c" ] && cp "$c" "$OUT/"; done

( cd "$OUT" && sha256sum ./* > MANIFEST.sha256 ) || true
echo "== deposit files:"; ls -la "$OUT"

# --- 4. optional: create a DRAFT deposition --------------------------------------------------
if [ "${1:-}" = "--upload" ]; then
  : "${ZENODO_TOKEN:?set ZENODO_TOKEN (Zenodo > Applications > Personal access tokens, scope deposit:write)}"
  API=https://zenodo.org/api/deposit/depositions
  echo "== creating a draft deposition"
  DEP=$(curl -sf -X POST "$API?access_token=$ZENODO_TOKEN" -H "Content-Type: application/json" \
        -d '{}') || { echo "FATAL: could not create the deposition"; exit 1; }
  ID=$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['id'])" "$DEP")
  BUCKET=$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['links']['bucket'])" "$DEP")
  echo "   deposition $ID"
  curl -sf -X PUT "$API/$ID?access_token=$ZENODO_TOKEN" -H "Content-Type: application/json" \
       -d @"$BENCH/zenodo/metadata.json" > /dev/null
  for f in "$OUT"/*; do
    echo "   uploading $(basename "$f")"
    curl -sf -X PUT --upload-file "$f" "$BUCKET/$(basename "$f")?access_token=$ZENODO_TOKEN" >/dev/null
  done
  echo "== DRAFT ready — review and publish by hand:"
  echo "   https://zenodo.org/uploads/$ID"
  echo "   Publishing mints the DOI and cannot be undone. Cite the CONCEPT DOI in the proposal,"
  echo "   so a later campaign becomes a new version behind the same reference."
fi
