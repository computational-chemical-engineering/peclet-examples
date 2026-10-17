# Bubble-column renders

A 3D picture of the production column ($D/h = 16$, 128 × 96 × 64) at one instant: the sixteen
bubbles as clear glass bodies, the two no-slip walls as faint panes with grey edges, and behind
the column a panel of the vertical liquid velocity, averaged over the depth (blue: down, along the
walls; orange: up, in the gas-laden core). The colour bar is added by `compose.py`. The background
is transparent; the glass refracts a neutral world, never the page, so the image reads on the
light and the dark site theme.

- Web figure: `../figures/bubbles_t100.png` (t = 100, 1152 × 1568, 256-colour palette PNG, < 1 MB).
- Finals (rendered at 3000 × 4000 with 1024 samples, trimmed to about 2900 × 3900): `~/Pictures/bubble-column/` (`bubbles_t100.png`,
  `bubbles_t150.png`, raw and with the colour bar).

The rendered state is from the page's own run (`../scripts/run_peclet.py`) at peclet-flow main
2ea4c65 (2026-10-17, RTX 5080): its checkpoint at t = 100 and t = 150. It is **not** the state
behind `../data/peclet_closed.npz`, which is an earlier, statistically equivalent run of the same
case (the swarm is chaotic; two builds part at round-off level after t ≈ 20).

## Data

Not in git (`data/` is gitignored). The checkpoints come from

```bash
python ../scripts/run_peclet.py --out run --t-end 100 && cp run/ckpt.npz ckpt_t100.npz   # ~ 22 min on an RTX 5080
python ../scripts/run_peclet.py --out run                && cp run/ckpt.npz ckpt_t150.npz   # resumes to t = 150
```

A checkpoint holds every bubble's own colour field on its moving box, in unwrapped cell
coordinates, and the velocity field.

## Pipeline

Suite venv (numpy, scipy, scikit-image, matplotlib; `pip install imagequant` for the web PNG) and
Blender 4.5 LTS (Cycles, OptiX; here `~/opt/blender-4.5.14-linux-x64` — Debian's Blender 4.3
cannot compile kernels for the RTX 5080, sm_120). Run from `data/`:

```bash
cd data
python ../bubbles_mesh.py ckpt_t100.npz mesh_t100.npz      # ~ 5 s: C_k = 1/2 isosurfaces + velocity panel
blender -b -P ../render.py -- mesh_t100.npz $PWD/bubbles_t100_raw.png 1200 1600 512 glass gpu
python ../compose.py bubbles_t100_raw.png ../../figures/bubbles_t100.png --width 1600 --colours 256 --check
blender -b -P ../render.py -- mesh_t100.npz $PWD/final_t100_raw.png 3000 4000 1024 glass gpu   # final
python ../compose.py final_t100_raw.png final_t100.png --width 4000
```

- **Interfaces:** each bubble is meshed whole from its own marker field (marching cubes at
  $C_k = 1/2$ on the box padded with $C = 0$, then Taubin smoothing), then shifted by whole periods
  so its centroid lies in the column. A bubble crossing the top/bottom or front/back periodic face
  is drawn whole on one side and may stick out of the column by up to a radius; none is cut. The
  mesh volume matches the marker volume to 0.2–0.3 % (`bubbles_mesh.py` prints it).
- **Panel:** $\sum_z (1-C)\,u_x / \sum_z (1-C)$ at cell centres, $C = \max_k C_k$; positive = down
  (the page's sign); the colour range is ±0.6 √(gD) (`UMAX` in `render.py` and `compose.py`).
- **Styles:** `glass` (used), `pearl` (glass with a milky body), `solid` (satin); append
  `_nopanel` to drop the velocity panel. `cpu` instead of `gpu` renders on 16 threads (the
  1200 × 1600 × 512 web render takes ~ 3 min there).
- **These renders** were made with `cpu` (the GPU was busy with the resolution check): the web
  figure in 164 s, each final in ~ 26 min. Re-renders are identical up to sampling noise.
- **Previews:** `450 600 32 glass cpu` renders in ~ 15 s.
