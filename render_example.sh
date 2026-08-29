#!/usr/bin/env bash
# Render one gallery example against the LOCAL fixed CUDA build, forcing re-execution
# (clears the example's freeze so the compiled-module change takes effect).
#   ./render_example.sh <example-name> [--keep-freeze]
set -euo pipefail
SUITE=/home/frankp/Codes/suite
QUARTO=$HOME/.local/quarto-1.6.40/bin/quarto
export QUARTO_PYTHON=$SUITE/.venv/bin/python
# The SDF-showcase batch (2026-08-30) builds: flow/dem CUDA + the core geom authoring module +
# the pure-Python coupling package. Override PECLET_LOCAL_BUILD in the environment for a page that
# wants the host (OpenMP) build instead -- the dem examples that make numeric claims need
# OMP_NUM_THREADS=1, which only the host build honours meaningfully.
export PECLET_LOCAL_BUILD="${PECLET_LOCAL_BUILD:-$SUITE/flow/build_l3_cuda:$SUITE/dem/build_l4_cuda:$SUITE/core/python/build_geom:$SUITE/coupling/python}"
export PATH=/usr/local/cuda-13.2/bin:$PATH
name="$1"; shift || true
target="examples/$name/index.qmd"
[ -f "$target" ] || { echo "no such example: $target"; exit 1; }
if [[ "${1:-}" != "--keep-freeze" ]]; then
  rm -rf "_freeze/examples/$name"     # force re-execution (freeze:auto replays otherwise)
fi
echo ">>> rendering $target with local build + fixes"
time "$QUARTO" render "$target"
echo ">>> done: $name"
