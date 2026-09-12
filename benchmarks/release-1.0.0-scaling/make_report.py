#!/usr/bin/env python
"""Render the standalone report the Zenodo record carries, from the same `index.qmd` the gallery
publishes — one source, so the archived report and the web page cannot drift.

A Zenodo record has to be readable on its own, without the site around it, so the HTML embeds its
images and CSS. Quarto renders the gallery; this uses pandoc, which is what a reader reproducing
the record is likely to have, and it resolves Quarto's own `{{< include >}}` shortcodes first.

    python make_report.py [outdir]
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "zenodo" / "build")
OUT.mkdir(parents=True, exist_ok=True)
NAME = "peclet-flow-1.0.0-scaling-report"

src = (HERE / "index.qmd").read_text()

# 1. front matter -> pandoc metadata we control (Quarto keys pandoc does not know are dropped)
fm = re.match(r"^---\n(.*?)\n---\n", src, re.S)
meta, body = (fm.group(1), src[fm.end():]) if fm else ("", src)
title = re.search(r'^title:\s*"(.*)"', meta, re.M)
subtitle = re.search(r'^subtitle:\s*"(.*)"', meta, re.M)

# 2. resolve Quarto includes
def include(m):
    return (HERE / m.group(1)).read_text()


body = re.sub(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}", include, body)

# 3. Quarto callouts -> plain fenced divs pandoc understands, keeping their titles as headings
body = re.sub(r':::+\s*\{\.callout-\w+(?:\s+collapse="\w+")?(?:\s+title="([^"]*)")?\}',
              lambda m: f'::: {{.callout}}\n**{m.group(1)}**\n' if m.group(1) else '::: {.callout}',
              body)

CSS = """
body{max-width:52rem;margin:2rem auto;padding:0 1.2rem;font-family:system-ui,-apple-system,
 "Segoe UI",Roboto,sans-serif;line-height:1.55;color:#0b0b0b;background:#fcfcfb}
h1,h2,h3{line-height:1.25} h1{font-size:1.7rem} h2{font-size:1.25rem;margin-top:2.2rem;
 border-bottom:1px solid #e6e5e0;padding-bottom:.3rem}
p.subtitle{color:#52514e;font-size:1.05rem;margin-top:-.4rem}
table{border-collapse:collapse;margin:1rem 0;font-size:.9rem;display:block;overflow-x:auto}
th,td{border:1px solid #e0dfda;padding:.3rem .55rem;text-align:right}
th:first-child,td:first-child{text-align:left}
thead th{background:#f3f2ee}
img{max-width:100%;height:auto}
code{background:#f3f2ee;padding:.1rem .25rem;border-radius:3px;font-size:.9em}
pre{background:#f3f2ee;padding:.7rem .9rem;border-radius:5px;overflow-x:auto}
pre code{background:none;padding:0}
.callout{border-left:3px solid #2a78d6;background:#f4f8fd;padding:.7rem 1rem;margin:1.2rem 0;
 border-radius:0 4px 4px 0}
blockquote{color:#52514e;border-left:3px solid #d8d7d2;margin-left:0;padding-left:1rem}
"""
css = OUT / "report.css"
css.write_text(CSS)
md = OUT / f"{NAME}.md"
md.write_text(body)

cmd = ["pandoc", str(md), "--standalone", "--embed-resources", "--toc", "--toc-depth=2",
       f"--css={css}", "--mathml", "--resource-path", str(HERE),
       "-o", str(OUT / f"{NAME}.html")]
if title:
    cmd += ["--metadata", f"title={title.group(1)}"]
if subtitle:
    cmd += ["--metadata", f"subtitle={subtitle.group(1)}"]
subprocess.run(cmd, check=True)
print(f"wrote {OUT / (NAME + '.html')}")

pdf = OUT / f"{NAME}.pdf"
try:
    subprocess.run(cmd[:1] + [str(md), "--standalone", "--toc", "--toc-depth=2",
                              "--resource-path", str(HERE), "-V", "geometry:margin=2.5cm",
                              "-V", "colorlinks=true", "--pdf-engine=lualatex",
                              *(["--metadata", f"title={title.group(1)}"] if title else []),
                              "-o", str(pdf)],
                   check=True, capture_output=True, timeout=600)
    print(f"wrote {pdf}")
except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
    tail = (e.stderr or b"").decode()[-400:] if hasattr(e, "stderr") else str(e)
    print(f"PDF skipped (the HTML report is self-contained): {tail}")
md.unlink()
css.unlink()
