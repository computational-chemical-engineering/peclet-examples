#!/usr/bin/env bash
# Render one gallery example against the LOCAL fixed CUDA build, forcing re-execution
# (clears the example's freeze so the compiled-module change takes effect).
#   ./render_example.sh <example-name> [--keep-freeze]
set -euo pipefail
SUITE=/home/frankp/Codes/suite
# Quarto lives in the suite venv (the one venv every project activates), not on the system
# PATH and not in a tarball under ~/.local — that tarball was 1.6.40, three minor versions
# behind, and was deleted on 2026-09-18.
QUARTO=$SUITE/.venv/bin/quarto
export QUARTO_PYTHON=$SUITE/.venv/bin/python
# The SDF-showcase batch (2026-08-30) builds: flow/dem CUDA + the core geom authoring module +
# the pure-Python coupling package. Override PECLET_LOCAL_BUILD in the environment for a page that
# wants the host (OpenMP) build instead -- the dem examples that make numeric claims need
# OMP_NUM_THREADS=1, which only the host build honours meaningfully.
# The build trees this renders against. They must match the peclet the page CLAIMS to run on: every
# build_*_cuda tree in the suite on 2026-09-12 predated its module's own 1.0.0 release commit, which
# is why the gallery's 1.0.0 re-render built build_gal_cuda in each repo first.
#   cd <mod> && cmake -S . -B build_gal_cuda -DCMAKE_BUILD_TYPE=Release \
#       -DCMAKE_PREFIX_PATH="$SUITE/extern/install/nvidia-cuda" && cmake --build build_gal_cuda -j
# NOTE the interpreter must NOT have peclet wheels installed, or a page whose bootstrap mishandles
# this variable silently renders against the WHEEL instead of your build and you never find out.
export PECLET_LOCAL_BUILD="${PECLET_LOCAL_BUILD:-$SUITE/core/python/build_gal_cuda:$SUITE/flow/build_gal_cuda:$SUITE/dem/build_gal_cuda:$SUITE/voro/build_gal_cuda:$SUITE/pnm/build_gal_cuda:$SUITE/coupling/build_gal_cuda}"
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
