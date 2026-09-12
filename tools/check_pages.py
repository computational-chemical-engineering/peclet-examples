#!/usr/bin/env python3
"""Do the gallery pages still RUN against the published peclet wheels?

The gallery's own CI renders from `_freeze/` and never imports peclet, so nothing here notices when
a release moves the API out from under a page — which is how the suite's landing page shipped a
quick start that raised `TypeError` at 1.0.0. This script closes that hole for the gallery: it
extracts the python chunks of each `index.qmd`, runs them against whatever peclet is installed, and
classifies the result.

An API break surfaces in the first seconds, in setup — building the solver, setting the domain BCs,
handing over the geometry. A page that is STILL RUNNING at the timeout has therefore passed the
part this check is about, and counts as `past-setup`, not as a failure: the alternative is running
hour-long simulations in CI to learn nothing new.

Two more checks run first, both cheap and needing nothing installed:

  SYNC   each page's committed `index.ipynb` — the file the Colab badge opens, and the only
         thing a Colab reader ever runs — must carry the same code as its `index.qmd`. They are a
         hand-maintained pair, so a fix applied to one and not the other ships broken to exactly
         the audience the badge is for. (Found that way: `rotating-sphere-torque` imported
         `peclet_coupling`, the source-layout name, which no wheel has ever exposed.)
  DATA   a data file a page reads must be in git. `.gitignore` ignores `*.npz`, so every one is
         tracked only by force-add — and hcs-clustering shipped depending on 5.2 MB that never was,
         which nobody else could render.

    python tools/check_pages.py                        # every page
    python tools/check_pages.py --changed-since origin/main
    python tools/check_pages.py examples/zick-homsy    # named pages
    python tools/check_pages.py --sync-only            # just the qmd/ipynb pairing, no execution

Exit status is non-zero if any page FAILED. Nothing is committed: the extracted script is written
into the page directory as `_apicheck.py`, run, and removed.
"""
import argparse, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNK = re.compile(r"```\{python[^}]*\}\n(.*?)```", re.S)
# A Jupyter magic or shell escape — NOT a python line that merely starts with `%`, such as the
# `% (label, N, lam)` continuing a printf-style format. The sigil must be followed by a word char.
MAGIC = re.compile(r"\s*(%%?\w+|!\w)")
PRELUDE = ("import matplotlib\nmatplotlib.use('Agg')\n"
           "import matplotlib.pyplot as plt\nplt.show = lambda *a, **k: None\n")


def page_source(qmd: Path) -> str:
    """The page's python chunks as one script, in reading order.

    The bootstrap chunk is KEPT: with peclet already installed its pip branch is dead, and dropping
    it loses the imports (os, the page's own helpers) that later chunks rely on.
    """
    out = [PRELUDE]
    for chunk in CHUNK.findall(qmd.read_text(errors="ignore")):
        out.append("\n".join(l for l in chunk.splitlines() if not MAGIC.match(l)))
    return "\n".join(out)


def check(qmd: Path, timeout: int):
    script = qmd.parent / "_apicheck.py"
    try:
        script.write_text(page_source(qmd))
        env = dict(os.environ, MPLBACKEND="Agg", PYVISTA_OFF_SCREEN="true",
                   OMP_NUM_THREADS=os.environ.get("OMP_NUM_THREADS", "4"), OMP_PROC_BIND="false")
        r = subprocess.run([sys.executable, script.name], cwd=qmd.parent, env=env,
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return qmd, "PASS", ""
        err = [l for l in r.stderr.strip().splitlines() if l.strip()]
        frame = next((l.strip() for l in reversed(err) if "_apicheck.py" in l), "")
        return qmd, "FAIL", f"{err[-1] if err else '?'}   [{frame}]"
    except subprocess.TimeoutExpired:
        return qmd, "PAST-SETUP", f"still running at {timeout}s"
    finally:
        script.unlink(missing_ok=True)


def changed_pages(base: str):
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", f"{base}...HEAD"],
                          capture_output=True, text=True).stdout.split()
    return sorted({ROOT / Path(f).parent / "index.qmd" for f in diff
                   if f.startswith(("examples/", "benchmarks/"))
                   and (ROOT / Path(f).parent / "index.qmd").exists()})


def executable(chunk: str) -> str:
    """A cell's actual code: `#|` lines are Quarto cell OPTIONS, and `quarto convert` rewrites them
    (it unquotes a fig-cap, say). Comparing them would report the converter's own round-trip as
    drift."""
    return "\n".join(l for l in chunk.splitlines() if not l.lstrip().startswith("#|")).strip()


def notebook_code(ipynb: Path):
    """The code cells of a committed .ipynb, as one string per cell."""
    nb = json.loads(ipynb.read_text(errors="ignore"))
    return [executable("".join(c["source"])) for c in nb["cells"] if c["cell_type"] == "code"]


DATA_SUFFIXES = {".npz", ".npy", ".csv", ".vti", ".vtp", ".h5", ".json", ".txt", ".dat"}
DATA_LITERAL = re.compile(r"""["']([^"'\n]+\.(?:npz|npy|csv|vti|vtp|h5|json|txt|dat))["']""")


def check_data(qmds) -> int:
    """A page may not depend on a data file that exists only on the author's machine.

    `.gitignore` ignores *.npz, so every data file is tracked only by force-add — and one page
    (hcs-clustering) shipped depending on 5.2 MB that was never added, which nobody else, Colab
    included, could render. Flags a referenced file that EXISTS here but is untracked; a path that
    does not exist is ignored, since the page may well write it before reading it.
    """
    tracked = set(subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                                 capture_output=True, text=True).stdout.split())
    bad = 0
    for qmd in qmds:
        rel = qmd.parent.relative_to(ROOT)
        missing = []
        for chunk in CHUNK.findall(qmd.read_text(errors="ignore")):
            for lit in DATA_LITERAL.findall(chunk):
                if lit.startswith(("http://", "https://")):
                    continue
                f = (qmd.parent / lit).resolve()
                try:
                    key = f.relative_to(ROOT).as_posix()
                except ValueError:
                    continue                       # outside the repo; not ours to police
                if f.exists() and key not in tracked and key not in missing:
                    missing.append(key)
        if missing:
            bad += 1
            print(f"DATA  FAIL  {rel}   untracked but required: {', '.join(missing[:4])}")
    if bad == 0:
        print(f"DATA  PASS  every data file a page reads is in git ({len(qmds)} pages)")
    return bad


def check_sync(qmds) -> int:
    """Each page's .ipynb mirror must carry the same code as its .qmd."""
    bad = 0
    for qmd in qmds:
        ipynb = qmd.with_suffix(".ipynb")
        rel = qmd.parent.relative_to(ROOT)
        if not ipynb.exists():
            continue                       # not every page ships a notebook
        a = [executable(c) for c in CHUNK.findall(qmd.read_text(errors="ignore"))]
        b = notebook_code(ipynb)
        if len(a) != len(b):
            bad += 1
            print(f"SYNC  FAIL  {rel}   {len(a)} qmd chunks vs {len(b)} notebook cells")
            continue
        drift = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if drift:
            bad += 1
            print(f"SYNC  FAIL  {rel}   cell {drift[0]} differs between index.qmd and index.ipynb")
            for x, y in zip(a[drift[0]].splitlines(), b[drift[0]].splitlines()):
                if x != y:
                    print(f"              qmd   {x[:110]}\n              ipynb {y[:110]}")
                    break
    if bad == 0:
        print(f"SYNC  PASS  every .ipynb mirror matches its .qmd ({len(qmds)} pages)")
    return bad


def main():
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--timeout", type=int, default=90, help="seconds before a page counts past-setup")
    a.add_argument("--workers", type=int, default=2)
    a.add_argument("--changed-since", metavar="REF", help="only pages touched since REF")
    a.add_argument("--sync-only", action="store_true",
                   help="only check that each .ipynb mirror matches its .qmd; execute nothing")
    a.add_argument("pages", nargs="*", help="page directories, e.g. examples/zick-homsy")
    a = a.parse_args()

    if a.pages:
        qmds = [ROOT / p if p.endswith(".qmd") else ROOT / p / "index.qmd" for p in a.pages]
    elif a.changed_since:
        qmds = changed_pages(a.changed_since)
    else:
        qmds = sorted(list((ROOT / "examples").glob("*/index.qmd"))
                      + list((ROOT / "benchmarks").glob("*/index.qmd")))
    if not qmds:
        print("no pages to check")
        return 0

    bad = check_sync(qmds) + check_data(qmds)
    if a.sync_only:
        return 1 if bad else 0

    with ThreadPoolExecutor(a.workers) as ex:
        for qmd, verdict, msg in ex.map(lambda q: check(q, a.timeout), qmds):
            bad += verdict == "FAIL"
            print(f"{verdict:10s} {qmd.parent.relative_to(ROOT)}   {msg}", flush=True)
    print(f"\n{len(qmds)} pages, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
