#!/usr/bin/env bash
# Render one gallery example against the LOCAL fixed CUDA build, forcing re-execution
# (clears the example's freeze so the compiled-module change takes effect).
#   ./render_example.sh <example-name> [--keep-freeze]
set -euo pipefail
SUITE=/home/frankp/Codes/suite
QUARTO=$HOME/.local/quarto-1.6.40/bin/quarto
export QUARTO_PYTHON=$SUITE/flow/.venv/bin/python
export PECLET_LOCAL_BUILD="$SUITE/flow/build_cuda_mphys:$SUITE/dem/build_cuda_mphys:$SUITE/coupling/build_cuda_mphys"
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
