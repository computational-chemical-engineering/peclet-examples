# Example style guide

How to write an example for this gallery. The two shipped examples are the
reference implementations — copy their shape. The goal of every example: a reader
sees what's possible, understands *why* it works, and can adapt it to their own
problem in minutes.

## 1. One directory per example

```
examples/<slug>/index.qmd      # the example (Quarto, executable)
examples/<slug>/*.png|data     # only if truly local & small; large assets go elsewhere (§7)
```

Reusable logic goes in `src/peclet_examples/` and is imported — never copy-paste a
solver-driving loop between examples. Keep the *teaching* code visible in the
notebook; push *plumbing* (dataset fetch, repetitive plotting) into the package.

## 2. Front matter

```yaml
---
title: "..."              # imperative, concrete ("Poiseuille through an SDF channel")
subtitle: "..."           # the one-line hook
author: "Peclet"
date: "YYYY-MM-DD"
categories: [flow, IBM, verification]   # method tags — power the gallery filters
jupyter: python3
---
```

## 3. Section skeleton

Every example has, in order:

1. **What you'll learn** — 2–4 sentences. Name the methods and the payoff.
2. **The problem / setup** — the physics and the math. Use display equations with
   labels (`$$ ... $$ {#eq-...}`) and reference them (`@eq-...`).
3. **The code**, in small cells with prose between them — never a wall of code.
4. **Results** — at least one figure; state the headline number in the text.
5. **Adapt this yourself** — concrete edits a reader can make (change the geometry,
   add coupling, go multi-rank). This section is mandatory.
6. **Reproduce this** — the exact commands (see §5).

## 4. Runs out of the box (the bootstrap rule)

A reader must be able to click "Open in Colab" and run top-to-bottom. Therefore:

- **Depend only on published packages.** Reader-facing cells install the solver
  from **PyPI** (`peclet`) — like a real user — via the standard bootstrap cell at
  the top (copy it from `poiseuille-ibm`). It is a no-op when the package is
  already importable or a local build is present (`PECLET_LOCAL_BUILD`).
- **Pure-NumPy examples** need no solver — their bootstrap only pulls the helper
  package (or nothing).
- Do **not** rely on repo-relative `sys.path` hacks or files that only exist in a
  clone.

## 5. Reproduce + freeze policy

- **Lightweight (pure NumPy/CPU) examples** execute in CI and in the browser.
- **Solver-backed examples** are executed by the author on hardware with `peclet`,
  and Quarto's `freeze: auto` caches the outputs under `_freeze/` (committed). CI
  then **renders only** — no GPU needed. Refresh a page's cache with
  `quarto render examples/<slug>/index.qmd --execute`.
- Every solver-backed example ends with a **Reproduce this** block giving both the
  PyPI path (`pip install -e .[sim]`) and the local-build path
  (`PECLET_LOCAL_BUILD=/path/to/suite/flow/build_mpi ... --execute`).

## 6. Figures & numbers

- Caption every figure (`#| fig-cap:`). Put the headline result in prose too, so
  it survives in search and screen readers.
- Keep figures small (≈4–5 in) and legible; label axes with units.
- Prefer showing a validation *against ground truth* (analytic, published data)
  over a pretty picture with no yardstick.

## 7. Large files — never in git

- **Videos → YouTube**; embed an iframe.
- **Datasets / fields (VTI/VTP/HDF5) → Zenodo or GitHub Release assets**, fetched
  on demand with [`pooch`](https://www.fatiando.org/pooch/) (checksummed). Put the
  fetch helper in `peclet_examples`.
- Git holds text + the small frozen PNG figures only (enforced by `.gitignore`).

## 8. When results surprise you

Examples are also a test of the packages. If an example produces an unexpected
number, a NaN, a divergence, or a rough edge in the API, **log it in
[`ISSUES.md`](ISSUES.md)** before working around it — that backlog is how the
gallery feeds fixes back into the suite. Don't silently tune parameters until it
looks fine.
