# Peclet Examples

Worked, **runnable** examples for the [`peclet`](https://pypi.org/project/peclet/)
simulation suite — GPU-accelerated particle dynamics, CFD, and the spatial-indexing
primitives they build on. Built with [Quarto](https://quarto.org): each example is
executed to produce its figures and numbers, ships as a downloadable notebook, and
links back to the exact solver API it uses.

**Live site:** https://computational-chemical-engineering.github.io/peclet-examples *(published by CI)*

## Examples

| Example | Methods | Runs where |
|---|---|---|
| [Channel MMS](examples/channel-mms/) | finite differences · MMS · grid convergence | anywhere (pure NumPy) |
| [Poiseuille cut-cell IBM](examples/poiseuille-ibm/) | cut-cell IBM · SDF · projection | Colab/CPU via the `peclet` PyPI wheel (frozen for CI) |

## Build locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                      # helpers + NumPy/Matplotlib
pip install jupyter nbclient nbformat

# Render everything (replays frozen solver outputs; re-executes pure-NumPy pages):
quarto render                          # -> _site/

# Re-execute a solver-backed page against a local source build of the suite:
PECLET_LOCAL_BUILD=/path/to/suite/flow/build_mpi OMP_NUM_THREADS=4 \
  quarto render examples/poiseuille-ibm/index.qmd --execute
#   ...or install the solver from PyPI and drop the env var:
#   pip install -e .[sim]
```

## How it's organised

```
src/peclet_examples/     installable helper package (imported by every example)
  mms.py                 pure-NumPy channel MMS
  channels.py            peclet.flow cut-cell Poiseuille driver
examples/<slug>/index.qmd  one worked example each
_freeze/                 committed execution outputs (so CI renders without a GPU)
_quarto.yml              site config (freeze: auto)
.github/workflows/       render + deploy to GitHub Pages
```

## Execution & publishing model

- **Lightweight examples** (pure NumPy) execute in CI and in the browser.
- **Solver-backed examples** are executed by the author on hardware with `peclet`
  installed; Quarto's `freeze` caches the outputs under `_freeze/`, which is
  committed. The Pages CI then **renders only** — no GPU, no compiled solver
  needed. Regenerate a page's freeze with `quarto render <page> --execute`.
- **GitHub Pages** is published by `.github/workflows/publish.yml` on push to `main`.

## Large files

Never committed to git (see `.gitignore`):

- **Videos → YouTube.** Pages embed an iframe; nothing is stored in-repo.
- **Datasets / fields (VTI/VTP/HDF5) → [Zenodo](https://zenodo.org)** (the suite
  already mints Zenodo DOIs) or GitHub Release assets, fetched on demand with
  [`pooch`](https://www.fatiando.org/pooch/) (checksummed).
- Git holds only text + the small frozen PNG figures.

## Contributing an example

Read the **[example style guide](STYLE_GUIDE.md)** — it defines the section
skeleton, the Colab bootstrap rule (reader-facing cells install `peclet` from
PyPI), and the freeze policy. Examples must run out-of-the-box on Colab.

Found something surprising while writing an example (a NaN, a divergence, a rough
API edge)? Log it in **[ISSUES.md](ISSUES.md)** — the gallery doubles as a test of
the packages and that backlog feeds fixes back into the suite.

## License

MIT — see [LICENSE](LICENSE).
