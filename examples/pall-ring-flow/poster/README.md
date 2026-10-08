# Pall-ring bed poster renders

Two poster images of flow through the 48-ring Pall-ring packing of `../../pall-ring-packing/`:
Stokes flow and Re_D = 100 (Re_D = ρ U D / μ with superficial velocity U and ring diameter D).
The rings are drawn whole at their DEM poses, one per ring, in one cream ceramic colour. Streamlines
are tiled periodically in x and z so that they also run past the rings at the edge of the cell. The
fluid shown extends 1.5 D below the bed and 1.0 D above it. The background is transparent.

Final renders (5000×7500, 1024 samples, 2026-10-08): `~/Pictures/pall-ring-poster/`
(`pall_ring_poster_stokes.png`, `pall_ring_poster_re100.png`).

## Data

The data are **not in git**: `data/` is gitignored, about 340 MB on the machine that made the
renders. Every file can be regenerated with the pipeline below.

| file | what |
|---|---|
| `ring_mesh.npz` | marching-cubes mesh of one Pall ring (principal frame, 360³ bake) |
| `flow_stokes.npz` | Stokes field, 112×320×112 at 32 cells/D, periodic in y (steady) |
| `flow_re100io.npz` | Re_D = 100 field, uniform inflow at −y and outflow at +y. Averaged over the last 30 % of 9000 steps: the wake above the bed is unsteady |
| `streams_stokes.npz`, `streams_re100io.npz` | streamlines, 1600 seeds at y = 0.25 D |
| `bed_sdf.npy` | bed SDF on the half-cell lattice; the tracer uses it to keep lines out of the walls |
| `grid_meta.npz` | grid metadata (`cells`, `h`, `yshift`) for `bedsdf.py` |
| `sim_*.log` | solver logs (probes, mean-vs-final difference) |

## Pipeline

Run everything from `data/`. Use the suite venv with `PYTHONPATH` pointing at a CUDA build of
`peclet.flow` (for `sim.py`) and at `peclet.geom` (for `ringmesh.py` and `bedsdf.py`). The renders
use Blender 4.5 LTS (Cycles, OptiX); here it was installed in `~/opt/blender-4.5.14-linux-x64`.

```bash
cd data
python ../ringmesh.py 360                                     # -> ring_mesh.npz (checks the tree against the pack file)
python ../sim.py 32 1500 flow_stokes.npz stokes               # ~ 12 min on an RTX 5080
python ../sim.py 32 9000 flow_re100io.npz re100io             # ~ 65 min
python ../bedsdf.py grid_meta.npz bed_sdf.npy                 # ~ 35 s
python ../streams.py flow_stokes.npz 1600 streams_stokes.npz 1 bed_sdf.npy
python ../streams.py flow_re100io.npz 1600 streams_re100io.npz 1 bed_sdf.npy
blender -b -P ../render.py -- poster $PWD/poster_stokes.png 5000 7500 1024 streams_stokes.npz   # ~ 3 min
blender -b -P ../render.py -- poster $PWD/poster_re100.png  5000 7500 1024 streams_re100io.npz
python ../compose.py poster_stokes.png poster_stokes_white.png white   # optional: flatten onto white
```

- **Previews:** `900 1350 128` renders in seconds.
- **Reproducibility:** the line selection uses fixed seeds, so re-renders are identical up to GPU
  sampling noise.
- **Other styles in `render.py`:** earlier artist impressions (`porcelain`, `glass`, `streaks`, the
  `*_cut` variants and others). The clipped-ring styles need `bed_mesh.npz` from
  `python ../bedmesh.py <h>` (and `cut`); the poster style does not.
- **Grid size:** NY must be a multiple of 32. With NY = 308 the pressure multigrid lost depth and a
  step was 9× slower.
