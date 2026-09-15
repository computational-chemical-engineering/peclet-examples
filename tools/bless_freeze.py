#!/usr/bin/env python3
"""Re-point a page's `_freeze/` cache at an edited source, WITHOUT re-running its simulations.

WHY THIS EXISTS. `_quarto.yml` sets `execute: freeze: auto`, and Quarto keys each page's cached
outputs on a hash of the page source — empirically, a plain MD5 of the `.qmd` file:

    md5sum examples/poiseuille-ibm/index.qmd
    == _freeze/examples/poiseuille-ibm/index/execute-results/html.json -> ["hash"]

So changing ONE character of prose — a typo, a sentence, a badge — invalidates the cache and asks
the next `quarto render` to execute the page again. On this site that means re-running the
simulation: minutes on a workstation, hours on the GPU pages, and on the Pages runner it means
failing outright, because that build deliberately has no solver installed. A markdown-only edit
costing a GPU campaign is absurd, and the absurdity has already bitten once (2026-09-14: a
download-notebook badge added to 44 pages turned the Pages build red and had to be reverted).

WHAT IT DOES. Recompute the hash and write it into the freeze, so `quarto render` accepts the cache
it already has. The outputs are not touched — they are still the outputs those code cells produced.

WHY IT IS SAFE, AND WHERE IT IS NOT. It refuses unless it can PROVE the code is unchanged, and it
proves it from the freeze itself rather than from git: `result.markdown` records every executed cell
verbatim as a ``` {.python .cell-code} ``` block, so the code that produced these outputs is sitting
in the cache next to them. The tool compares those blocks with the working file's chunks, ignoring
`#|` cell options (the same rule `check_pages.py` uses, and for the same reason — Quarto lifts them
into fence attributes). Prose may differ; a single character of code may not.

Proving it from the freeze rather than from git matters for the obvious workflow: edit, bless, edit
again. After a bless the hash names a source that was never committed, so a git-blob proof would
refuse the second edit for no good reason. The cache's own record does not have that problem.

`--force` skips that proof. It exists because "exceptional" sometimes means the history is gone (a
freeze committed without its source, a rebase that lost the blob), and a human who has checked by
hand should not be stuck. It will publish stale outputs if you are wrong. It prints what it could
not verify, every time.

    python tools/bless_freeze.py --check                 # what is stale, and would it be blessable
    python tools/bless_freeze.py examples/zick-homsy     # named pages
    python tools/bless_freeze.py --all                   # every page whose hash is stale
    python tools/bless_freeze.py --force <page>          # bless without the proof (prints a warning)

Exit status is non-zero if any requested page could not be blessed.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Quarto widens a fence when the cell body itself contains backticks, so a chunk can open with more
# than three — capture how many and require the same count to close, or a ``` inside a docstring
# ends the match early and the chunk is silently dropped.
CHUNK = re.compile(r"^(`{3,})\{python\}\n(.*?)^\1\s*$", re.M | re.S)


def executable(chunk: str) -> str:
    """A chunk's actual code. `#|` lines are Quarto cell OPTIONS, not code — the same exclusion
    check_pages.py makes, so the two tools agree on what "the code changed" means."""
    return "\n".join(l for l in chunk.splitlines() if not l.lstrip().startswith("#|")).strip()


HIDDEN = re.compile(r"^\s*#\|\s*echo:\s*false\s*$", re.M | re.I)


def code_chunks(text: str):
    return [executable(body) for _fence, body in CHUNK.findall(text)]


def hidden_count(text: str) -> int:
    """Chunks Quarto renders with NO code block: `#| echo: false` hides the source but still runs it,
    so the freeze legitimately carries fewer blocks than the page has chunks."""
    return sum(1 for _fence, body in CHUNK.findall(text) if HIDDEN.search(body))


def is_subsequence(small, big) -> bool:
    it = iter(big)
    return all(any(x == y for y in it) for x in small)


def freeze_json(qmd: Path):
    """The execute-results json for a page, or None. `_freeze/<dir>/<stem>/execute-results/*.json`."""
    rel = qmd.relative_to(ROOT)
    d = ROOT / "_freeze" / rel.parent / rel.stem / "execute-results"
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"))
    return files[0] if files else None


# Quarto writes the executed cells back into the freeze as ``` {.python .cell-code ...} ``` — note
# the space after the fence, that `#|` options have been lifted into the attribute list, and that
# the fence may be SIX backticks where the cell body contains a three-backtick line.
FROZEN = re.compile(r"^(`{3,}) *\{\.python \.cell-code[^}]*\}\n(.*?)^\1\s*$", re.M | re.S)


def frozen_code(data: dict):
    """The code the cached outputs were produced from, straight out of the freeze."""
    md = data.get("result", {}).get("markdown", "")
    return [body.strip() for _fence, body in FROZEN.findall(md)]


def bless(qmd: Path, force: bool, check_only: bool) -> int:
    """0 = ok (blessed, or already current), 1 = refused."""
    name = qmd.relative_to(ROOT).parent.as_posix()
    fj = freeze_json(qmd)
    if fj is None:
        print(f"  SKIP   {name}: no freeze — nothing to bless (the page has never been executed)")
        return 0

    data = json.loads(fj.read_text())
    stored = data.get("hash")
    current = hashlib.md5(qmd.read_bytes()).hexdigest()
    if stored == current:
        print(f"  OK     {name}: hash already matches; quarto will reuse the cache")
        return 0

    if not force:
        before = frozen_code(data)
        after = code_chunks(qmd.read_text(errors="ignore"))
        if not before and after:
            print(f"  REFUSE {name}: the freeze records no executed cells, so there is nothing to "
                  f"check the {len(after)} chunk(s) against. --force to override.")
            return 1
        text = qmd.read_text(errors="ignore")
        hidden = hidden_count(text)
        # `before` omits any `echo: false` chunk, so it must be a SUBSEQUENCE of the page's chunks,
        # and the shortfall must be exactly the hidden ones. Subsequence alone would wave through an
        # ADDED chunk, whose output the cache does not contain; the count pins that down.
        if not (is_subsequence(before, after) and len(after) - len(before) == hidden):
            print(f"  REFUSE {name}: the code no longer matches what produced these outputs "
                  f"({len(before)} block(s) in the freeze, {len(after)} chunk(s) in the page, "
                  f"{hidden} hidden) — this page needs re-executing, not blessing.")
            return 1

    if check_only:
        print(f"  WOULD  {name}: prose-only change, {stored[:8]} -> {current[:8]}")
        return 0

    # Patch the hash TEXTUALLY. A json round-trip would rewrite the cached markdown too — Python
    # escapes non-ASCII by default where Quarto writes UTF-8, and Quarto ends the file without a
    # newline — turning a one-field edit into a whole-file diff over outputs nobody changed.
    raw = fj.read_text(encoding="utf-8")
    needle = f'"hash": "{stored}"'
    if raw.count(needle) != 1:
        print(f"  REFUSE {name}: cannot locate the hash field to patch cleanly")
        return 1
    fj.write_text(raw.replace(needle, f'"hash": "{current}"', 1), encoding="utf-8")
    tag = "FORCED" if force else "BLESS "
    print(f"  {tag} {name}: {stored[:8]} -> {current[:8]}"
          + ("   (UNVERIFIED — outputs may be stale)" if force else ""))
    return 0


def pages(args) -> list:
    if args.all or (args.check and not args.pages):
        return sorted(p for p in ROOT.rglob("*.qmd")
                      if "_freeze" not in p.parts and "_site" not in p.parts
                      and freeze_json(p) is not None)
    out = []
    for a in args.pages:
        p = Path(a)
        if not p.is_absolute():
            p = ROOT / a
        out.append(p if p.suffix == ".qmd" else p / "index.qmd")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="*", help="page dirs or .qmd paths")
    ap.add_argument("--all", action="store_true", help="every page with a freeze")
    ap.add_argument("--check", action="store_true", help="report only; change nothing")
    ap.add_argument("--force", action="store_true",
                    help="bless WITHOUT proving the code is unchanged (can publish stale outputs)")
    args = ap.parse_args()
    if not (args.pages or args.all or args.check):
        ap.error("name a page, or pass --all / --check")

    if args.force:
        print("!! --force: blessing without checking the code. If the code did change, the site "
              "will publish outputs that no longer correspond to it.\n")

    bad = 0
    for qmd in pages(args):
        if not qmd.is_file():
            print(f"  REFUSE {qmd}: no such page")
            bad += 1
            continue
        bad += bless(qmd, args.force, args.check)
    if bad:
        print(f"\n{bad} page(s) not blessed — they need a real re-execution, or --force.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
