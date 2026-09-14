# peclet 1.0.0 scaling deposit — decision log (append only)

2026-09-12  Deposit excludes FoxBerry and every external code.
  Options: (a) carry the FoxBerry head-to-head into the deposit; (b) peclet-only; (c) peclet plus
  the public codes (CaNS/incflo/OpenFOAM) already in the gallery.
  CHOSEN (b), by the user. Reasoning: FoxBerry is an in-house TU/e code
  (gitlab.tue.nl:SMM/Berry_Project) — not public, so its numbers are not independently
  verifiable by a reader, and a DOI-minted head-to-head against an unpublished code cited in an
  NWO proposal is a different act from a gallery page. The gallery keeps the comparison.
  Carried by: this campaign's scope. Reversible by: adding a reference series to the plots.

2026-09-12  One Zenodo Dataset record covering all four ladders (user).

2026-09-13  Work in the plain peclet-examples checkout, not a worktree.
  The work is a new additive directory in a repo with no build; other sessions are active in that
  checkout (its tree was dirty with another session's re-render), so every commit stages named
  paths only. Reversible by: git mv into a worktree.

2026-09-13  Provisioning is a campaign-local install script, not suite tools/hpc/install_snellius.sh.
  Options: (a) run the family site installer; (b) a trimmed copy carried inside the artifact.
  CHOSEN (b): the deposit needs morton+core+flow only, and a 3-hour GPU build that dies on voro
  costs budget and a day. The copy names its ancestor. Reversible by: calling the suite script.

2026-09-13  ONE TREE PER BACKEND on the cluster ($PROJ/suite-v1.0.0-bench-<target>).
  Caught before it produced data: the first submission pointed both the CUDA and the host build at
  one checkout, one extern prefix and one venv, so whichever finished last would own the installed
  flow. Both jobs cancelled (26628180/26628182) and the mixed tree deleted. Any result from a tree
  two builds shared is SUSPECT, not merely stale.

2026-09-13  Single case family for all four ladders: triply periodic, body-force-driven Stokes flow
  through a periodic sphere packing, cut-cell IBM.
  Options: (a) reproduce the inlet/outlet channel case for the strong ladders and use a periodic
  bed for the weak one; (b) one periodic case family everywhere.
  CHOSEN (b): the strong and weak ladders then share rung 1 exactly, the same physics gate applies
  to every run, one bed artifact serves the study, and it avoids the known open-face IBM defect.
  Reversible by: a BC=channel path in the driver (not written).

2026-09-13  The weak ladder TILES one unit cell rather than packing a fresh bed per rung.
  Options: (a) a per-rung random bed (what the earlier porous study did); (b) exact periodic
  replication of one unit cell.
  CHOSEN (b): with (a) the permeability scatter across rungs is bed statistics, which is noise in
  the physics gate. With (b) the tiled problem is the SAME problem, so the observable is one number
  every rung must reproduce, and disagreement means a defect. Stated in the report: the large
  rungs are replications, not independent beds.

2026-09-13  New unit cell (1043 spheres, R = 18 cells at 384³) rather than reusing the committed
  5000-sphere bed (R = 10.7 cells at 384³).
  Reason: the porous-scaling refine ladder found cut-cell k converged to four digits at R >= 16, so
  R = 18 makes the physics gate a statement about the solver rather than about an under-resolved
  bed. Grown with the RELEASED peclet-dem 1.0.0 wheel from PyPI, so the artifact is reproducible
  with pip. Reversible by: PACK=.

2026-09-13  Pressure multigrid depth is requested as deep as the grid admits (LEVELS=10, clamped),
  not the shipped default of 4.
  Reason: depth is a property of the grid, not a tuning constant, and a fixed shallow default would
  make the study measure the default instead of the solver. This is the ONE stated departure from
  the shipped 1.0.0 configuration; everything else (MG-PCG rtol 1e-8, telescoping, the 'auto'
  bottom, the velocity-MG auto rule, the coupled momentum tolerance) is untouched, and
  PECLET_CORE_GPU_AWARE_MPI is left UNSET so the shipped auto-detection is what gets measured.
  LEVELS=4 is reported as a sensitivity point at one rung. Reversible by: LEVELS=.

2026-09-13  The permeability march is OPT-IN, not run at every rung.
  A 600-step march at 32 GPUs is ~25 minutes for a number that is identical at every rung. Instead
  every run reports <u> after its fixed WARMUP+NSTEPS from rest — one allreduce, and a sharper gate
  because it compares a transient the distributed step must reproduce bit-for-bit. The march runs
  at a few rungs to produce the permeability itself.

2026-09-13  CPU ladder takes EXCLUSIVE nodes at every rung.
  Trade: exclusive removes shared-node interference (worth more in a citable record) but gives the
  sub-node rungs (24/48/96) up to 8x the per-rank memory bandwidth of the full-node rungs, which
  flatters the baseline and understates the reported efficiencies. Stated in the report; the
  apples-to-apples segment is 192 -> 1536.

2026-09-13  The reproducible 16-GPU strong-scaling anomaly is REPORTED, not diagnosed.
  At 16 GPUs the fixed-problem step (926 ms) is slower than at 8 (857 ms), and a second allocation
  reproduces it to 1.00x — so it is structural, not node placement. It lives entirely in the
  projection phase (303 -> 514 ms) with an identical multigrid hierarchy at both rungs.
  Options: (a) spend GPU budget bisecting it (decomposition shape, halo pattern, coarse-level
  behaviour); (b) report the measurement and name the untested hypothesis.
  CHOSEN (b). The deposit's scope is what 1.0.0 does, not why; a reproducible anomaly reported with
  its phase attribution is a contribution, and smoothing it away or calling it noise would be the
  failure. The suspicion (8 GPUs give cubic per-rank blocks, 16 give 1:2:2) is stated AS a
  hypothesis. Follow-up belongs in the suite's own scaling work, not here.

2026-09-13  The Taylor-Green run is presented as a CONTROL, not as "the cost of the IBM".
  The first draft said the geometry costs a factor 1.0x in step time. That comparison is not
  like-for-like: the control advects and the bed case is creeping (advection off), so the two differ
  in physics as well as geometry. The page now says so explicitly and quotes only what the control
  does isolate — the 3.7x pressure-iteration ratio, and the weak-efficiency gap (88 % vs 79 %).

2026-09-13  The equivalence gate groups by SOLVER CONFIGURATION as well as by problem.
  set_velocity_multigrid_auto turns the velocity multigrid on below ~65k cells/rank, so the
  1536-core rungs run a different momentum solver from the rest of the ladder. Ungrouped, the gate
  reported 3.7e-07 and hid a 8.4e-11 agreement inside it. Grouped, the record reads: 8.4e-11 over
  25 runs and two backends; 1.4e-16 for the control; the three switched rungs identical to the last
  digit. The distance between configurations is reported as its own measurement.

2026-09-14  This session's `git push` carried another session's deliberately-unpushed commits.
  The gallery re-render campaign (peclet-examples PROGRESS.md, Claude-Session 01RCL1exd...) was
  holding 37 commits that port every page to the 1.0.0 API, because pushing them without the
  regenerated `_freeze/` outputs turns the Publish job red — which its own notes said in as many
  words. Pushing this benchmark from the shared checkout carried them to origin, and the Publish
  job has been red since (runs 34728504367, 34735258567, 34819804007). A later push carried their
  remaining commit 45aafa7 too: their commits sit BELOW ours in history, so pushing ours cannot
  avoid pushing theirs without a rebase.
  Lesson for a shared checkout: `git push` is not scoped to your own work. Check
  `git log --oneline origin/main..HEAD` BEFORE pushing, not after, and if it carries commits you
  did not write, find out whether they were being held.
  Mitigation: no content of theirs is live — every failed build stops before the deploy job.

2026-09-14  The page was published by a surgical one-off deploy, not by fixing the red pipeline.
  Options: (a) wait for the re-render campaign (six pages still need renders, two wanting a
  multi-hour serial GPU budget); (b) set Quarto `freeze: true` so stale pages render from old
  outputs; (c) install peclet in the publish CI; (d) deploy the last green tree plus this page.
  CHOSEN (d). (b) would publish 1.0.0 prose against pre-1.0.0 figures on 47 pages — the campaign
  had already flagged that DEM numbers move ~20 % between those renders, so it would put
  internally inconsistent pages on a public gallery. (c) would execute those pages on a CPU CI and
  publish numbers from a machine the pages were not authored against. (a) was the user's explicit
  no.
  (d) publishes the site EXACTLY as it was already live plus one static page: base cde8b25 (the
  last green deploy), `git diff` against it touches only this page's directory and its index card,
  and the page has zero code cells so nothing executes. Branch `deploy/benchmark-1.0.0-page`,
  run 34819466850. The `github-pages` environment is main-only, so that branch was allowed
  temporarily and THE POLICY WAS REMOVED IMMEDIATELY AFTER — verified back to main-only.
  Reversible by: the campaign's own full deploy, which supersedes it entirely.
