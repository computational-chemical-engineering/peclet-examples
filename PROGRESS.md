# Overnight build progress

Working through a batch of single-phase-flow benchmark examples for the gallery.
Each example is **self-contained** (creates its own SDF, sets all parameters
inline — no `channels.py`-style imports), executed against the local CPU build
(`PECLET_LOCAL_BUILD=…/flow/build_mpi`), frozen, committed, and pushed.

Legend: [x] done+pushed · [~] in progress · [ ] todo · [!] blocked/documented

## Tasks

- [x] Diagnose poiseuille "error" → metric artifact, not a solver bug (ISSUES.md)
- [~] Remove non-peclet `channel-mms`; drop helper-module imports; self-contained
- [ ] Rewrite `poiseuille-ibm`: self-contained, **pointwise** error, both meshes
- [ ] flow: rename `verify_poiseuille_sdflow.py`→`verify_poiseuille_flow.py`, pointwise metric
- [ ] `pipe-poiseuille`: Hagen–Poiseuille in a cylindrical SDF pipe (test pointwise exactness)
- [ ] `cylinder-vortex-street`: flow past a cylinder vs Re; Strouhal number vs literature
- [ ] `zick-homsy`: SC grid convergence (2nd order) + parametric K(φ) + BCC/FCC lattices
- [ ] `random-packed-bed`: peclet.dem packing → characterize → permeability stats + convergence
- [ ] `lid-driven-cavity`: vs Ghia et al. (1982)
- [ ] `backward-facing-step`: Gartling reattachment vs Re
- [ ] `taylor-green`: analytic viscous decay
- [ ] (stretch) other classics: Couette, Womersley, Kármán data, Stokes problems

## Findings / bugs (see ISSUES.md for full)
- Poiseuille metric artifact (resolved — reframed as exactness demo)
- Inflow/outflow NaN at under-resolved/odd config — BFS+channel scripts work at
  proper resolution, so likely config not a solver bug; will confirm per-example.

## Notes for future me
- Local CPU build: `PECLET_LOCAL_BUILD=/home/frankp/Codes/suite/flow/build_mpi`,
  `OMP_NUM_THREADS=4 OMP_PROC_BIND=spread OMP_PLACES=threads`.
- Quarto binary: scratchpad `quarto-1.5.57/bin/quarto`. Render: `quarto render`.
- Regenerate a Colab notebook after editing a qmd: `quarto convert examples/<slug>/index.qmd`.
- Keep grids modest — CPU-only overnight. Commit+push each example when green.
