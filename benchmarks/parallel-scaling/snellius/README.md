# Snellius run pack — parallel-scaling study

All scripts submit from this directory, write JSONs into `results/snellius-*/`, and are
**resumable** (existing JSONs are skipped — delete a JSON to re-measure it). Keep walltimes
short: `gpu_h100` is usually full and short jobs backfill in hours instead of days.

## 0. One-time setup

Fixed locations everything below assumes (override with `SUITE=` / `EXAMPLES=`):

| what | path |
|---|---|
| suite (solver + submodules) | `/projects/0/prjs1022/peclet/suite` |
| this repo | `/projects/0/prjs1022/peclet/peclet-examples` |
| GPU build (H100) | `$SUITE/flow/build_cuda_mpi` — `tgv_weak_gpu.sh`'s default `BUILD` |
| CPU build (genoa) | `$SUITE/flow/build_omp_mpi` — `tgv_genoa.sh`'s default `BUILD` |
| shared venv | `$SUITE/flow/.venv` (nanobind + mpi4py + cupy) |
| results | `<this dir>/results/snellius-{h100,genoa}/` |

```bash
cd /projects/0/prjs1022/peclet/suite && git pull --recurse-submodules
cd ../peclet-examples && git pull
cd examples/wall-bounded-turbulence
sbatch install_snellius.sh h100     # -> flow/build_cuda_mpi  (add FRESH=1 when CUDA/arch changed)
# CPU build must go through --wrap: install_snellius.sh's own #SBATCH header asks for a GPU, which
# the genoa partition rejects, and SLURM_SUBMIT_DIR must point at the dir holding snellius_env.sh.
sbatch -p genoa --nodes=1 --ntasks=1 --cpus-per-task=48 --time=02:00:00 -J peclet-build-cpu \
  --wrap="cd $PWD && SLURM_SUBMIT_DIR=$PWD bash ./install_snellius.sh cpu"   # -> flow/build_omp_mpi
# ^ both recreate flow/.venv with --clear, so run the h100 one LAST (it re-adds cupy).
# CaNS build, once:
cd ../../benchmarks/parallel-scaling/snellius && sbatch --nodes=1 refs_genoa.sh build
```

`submit_mgfix.sh` (§2b) does all of this for you, skipping builds that are already current.

**Mode selection is always a script ARGUMENT, never a leading env var** — SURF's sbatch drops
those (the channel campaign's FRESH=1 lesson). `sbatch ... tgv_genoa.sh weak`, `refs_genoa.sh
cans`, `tgv_weak_gpu.sh levers`.

## 1. GPU weak scaling 1–32 H100 (task: extend the curve + per-phase split)

**The GPU build must be rebuilt first** (the driver needs the tolerance-stop / mean-removal APIs
from the perf commits — an older `build_cuda_mpi` fails every run with a TypeError):

```bash
cd /projects/0/prjs1022/peclet/suite && git pull --recurse-submodules
cd ../peclet-examples/examples/wall-bounded-turbulence
sbatch install_snellius.sh h100          # incremental flow rebuild; note the job id -> $BUILD
```

Then queue the whole campaign with dependencies (each job measures ONLY its argument N —
queue-parallel safe):

```bash
cd ../../benchmarks/parallel-scaling/snellius
sbatch --dependency=afterok:$BUILD --nodes=1 tgv_weak_gpu.sh 1
sbatch --dependency=afterok:$BUILD --nodes=1 tgv_weak_gpu.sh 2
sbatch --dependency=afterok:$BUILD --nodes=1 tgv_weak_gpu.sh 4
sbatch --dependency=afterok:$BUILD --nodes=2 tgv_weak_gpu.sh 8
sbatch --dependency=afterok:$BUILD --nodes=4 tgv_weak_gpu.sh 16
sbatch --dependency=afterok:$BUILD --nodes=8 tgv_weak_gpu.sh 32
# lever ablation (Chebyshev / mean-scope-all / GraphAMG bottom / host-staged halo):
sbatch --dependency=afterok:$BUILD --nodes=2 tgv_weak_gpu.sh levers   # at N=8
sbatch --dependency=afterok:$BUILD --nodes=4 tgv_weak_gpu.sh levers   # at N=16
```

Cost: each N is a ≲2-minute measurement; the whole campaign is a few k SBU. gpu_h100 queue wait
dominates — short walltimes (45 min) backfill well.

## 2. Genoa CPU

```bash
sbatch --nodes=1 tgv_genoa.sh                       # hybrid mix sweep (192x1 … 12x16)
# then weak scaling at the winning mix (default 96x2). NOTE: mode is a script ARGUMENT —
# SURF sbatch drops leading env vars (the FRESH=1 lesson):
for n in 1 2 4 8; do sbatch --nodes=$n tgv_genoa.sh weak; done
```

## 2b. Re-measurement after the MG residual-halo fix (flow 5d77deb) — ONE COMMAND

The pressure V-cycle used to restrict a residual computed with one-colour-stale ghosts, which made
its convergence rate depend on the DECOMPOSITION: the genoa mix ran 12 pressure iters/step at
12–24 ranks/node against 8.1 at 96 (the whole "fat ranks are slower" penalty). With the fix,
iteration counts are decomposition-independent and lower everywhere (workstation: flat 4.0 at
np=1…24 on one grid; single RTX 5080 192³: 105.4 → 60.0 ms/step). **Every peclet number in the
study predates this** — CPU and GPU alike. The references (CaNS / incflo / OpenFOAM) are unaffected
and do NOT need re-running.

```bash
ssh snellius
cd /projects/0/prjs1022/peclet/peclet-examples/benchmarks/parallel-scaling/snellius
bash submit_mgfix.sh all         # DRY_RUN=1 first if you want to see the sbatch lines
```

`submit_mgfix.sh` (login node, not a batch script) does the whole thing:

1. `git pull` on `/projects/0/prjs1022/peclet/suite` (with submodules) and on `peclet-examples`
   (`PULL=0` to skip).
2. **Builds only what is stale** — it compares `flow/build_omp_mpi` and `flow/build_cuda_mpi`
   against `flow/src` + `core/include` mtimes and submits `install_snellius.sh cpu` (genoa) and/or
   `install_snellius.sh h100` only when needed; every measurement is then queued with
   `--dependency=afterok:<build>`. A current build is left alone and the jobs start immediately.
   Both builds share `flow/.venv` (the installer recreates it with `--clear`), so when both are
   stale the CPU build runs first and the GPU build finishes the venv (it re-adds cupy).
3. Queues, with result tag `mgfix` (`TAG=` to change; `REPEATS=2` adds a second genoa draw):
   - **genoa**: 1-node hybrid mix (192×1 … 12×16) + weak sweeps n=1,2,4,8 at **12×16 (fat)** and
     **96×2 (thin)** — the fat-vs-thin comparison this fix was made for.
   - **H100**: weak 1,2,4,8,16,32 GPUs (`MAXGPU=` caps it) + the lever ablation at 8 and 16. The
     ablation is worth redoing: Chebyshev went 17 → 5 iterations locally, and it is the lever the
     old ablation rejected as 2.6× worse.

Modes: `all` (default) | `cpu` | `gpu` | `build` (submit builds, queue nothing).

**The tag is not optional decoration:** `run_one` skips a JSON that already exists, so without a new
tag the pre-fix results would be silently re-reported as the new numbers.

Results land in, and are read/pulled from, these exact paths:

```bash
# on Snellius
.../parallel-scaling/snellius/results/snellius-genoa/{mix_r*_t*_mgfix.json,weak_n*_r{12,96}_t{16,2}_mgfix.json}
.../parallel-scaling/snellius/results/snellius-h100/weak_np{1,2,4,8,16,32}_mgfix.json

squeue -u $USER -o '%.10i %.14j %.2t %.10M %.6D %R'      # watch
grep -H '"pressure_iters_per_step"' results/snellius-genoa/mix_*_mgfix.json   # the first thing to read

# LOCALLY, to bring everything home:
rsync -av snellius:/projects/0/prjs1022/peclet/peclet-examples/benchmarks/parallel-scaling/snellius/results/ \
  ~/Codes/peclet-examples/benchmarks/parallel-scaling/results/
cd ~/Codes/peclet-examples/benchmarks/parallel-scaling && python plot_snellius.py
```

**What to look for:** `pressure_iters_per_step` for 12×16 and 96×2 should now AGREE — that is the
fix's falsifiable prediction. Per-node throughput parity follows only if the remaining intra-rank
thread scaling holds up: on the workstation a 24-thread rank is still ~24% slower than 12 ranks × 2
threads at 320³, all of it inside `projection`, so 12×16 may land a little behind 96×2 even with
equal iteration counts. Arithmetic on the old draws: 12×16 was 4561 ms @ 12 iters vs 96×2's 3191 @
8.1; removing the iteration penalty alone lands 12×16 at ≈3080 ms ≈ parity. Genoa node-set
variability is ±2.5× on single draws — use `REPEATS=2` (or resubmit with `TAG=mgfix2`) before
believing any single number.

If you prefer to do it by hand, the equivalent submissions are:

```bash
sbatch --nodes=1 tgv_genoa.sh mix mgfix
sbatch --nodes=8 --export=ALL,RPN=12,THREADS=16 tgv_genoa.sh weak mgfix
sbatch --nodes=8 --export=ALL,RPN=96,THREADS=2  tgv_genoa.sh weak mgfix
sbatch --nodes=2 tgv_weak_gpu.sh 8 mgfix
sbatch --nodes=2 tgv_weak_gpu.sh levers mgfix
```

## 3. References

```bash
sbatch --nodes=1 refs_genoa.sh incflo-build                       # once (AMReX superbuild, ~15 min)
sbatch --nodes=1 --time=03:00:00 refs_genoa.sh openfoam-build     # once (ESI v2412 source, ~1 h)
for n in 1 2 4; do sbatch --nodes=$n refs_genoa.sh cans; done
for n in 1 2 4; do sbatch --nodes=$n refs_genoa.sh incflo; done
for n in 1 2; do sbatch --nodes=$n refs_genoa.sh openfoam; done   # serial blockMesh caps size
```

## 4. Bring results home

```bash
rsync -av snellius:/projects/0/prjs1022/peclet/peclet-examples/benchmarks/parallel-scaling/snellius/results/ \
  ~/Codes/peclet-examples/benchmarks/parallel-scaling/results/
```

Then regenerate figures locally (`plot_workstation.py` + the Snellius plot script) and rebuild the
page.
