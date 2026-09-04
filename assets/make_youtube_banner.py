#!/usr/bin/env python3
"""Build the YouTube channel banner for @PecletHPC, in the same visual language as
assets/peclet-banner.jpg (dark navy, teal 'Pe' disc, Liberation Sans).

YouTube shows a different crop of one image on every device:

    2560 x 1440   the file it wants (safe up to 6 MB)
    2560 x 423    what a desktop browser shows
    1855 x 423    tablet
    1235 x 338    TV-safe centre — everything that must always be readable lives here

so the type is placed inside that 1235 x 338 box and the rest of the canvas is only
background that some devices happen to reveal.

    python make_youtube_banner.py [out.png]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 2560, 1440
SAFE_W, SAFE_H = 1235, 338
BG = (18, 23, 31)
TEAL = (13, 148, 136)
WHITE = (245, 247, 250)
GREY = (150, 158, 170)

FONTS = Path("/usr/share/fonts/truetype/liberation")
BOLD = FONTS / "LiberationSans-Bold.ttf"
REG = FONTS / "LiberationSans-Regular.ttf"


def particles(img: Image.Image, seed: int = 7) -> None:
    """The drifting speck motif from the website banner — a bed being carried by a flow.

    Kept well outside the safe box, and dim, so it never competes with the wordmark.
    """
    rng = np.random.default_rng(seed)
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(300):
        # a plume sweeping up to the right, starting clear of the safe box's right edge
        u = rng.random()
        x = W * (0.76 + 0.26 * u) + rng.normal(0, 30)
        y = H * 0.5 - (u ** 1.7) * H * 0.20 + rng.normal(0, H * 0.055)
        r = 2.0 + 7.0 * rng.random() * (0.35 + u)
        a = int(18 + 90 * rng.random() * u)
        d.ellipse([x - r, y - r, x + r, y + r], fill=TEAL + (a,))


def fitted(path: Path, text: str, want: int, avail: int) -> ImageFont.FreeTypeFont:
    """The largest size at or below `want` whose `text` still fits in `avail` pixels.

    The tagline is long and the TV-safe box is only 1235 px wide; measuring beats guessing,
    and it keeps the banner correct if the wording is ever edited.
    """
    for size in range(want, 11, -2):
        f = ImageFont.truetype(str(path), size)
        if f.getbbox(text)[2] <= avail:
            return f
    return ImageFont.truetype(str(path), 12)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else
               Path(__file__).parent / "peclet-youtube-banner.png")
    img = Image.new("RGB", (W, H), BG)
    particles(img)
    d = ImageDraw.Draw(img)

    x0, y0 = (W - SAFE_W) // 2, (H - SAFE_H) // 2

    # --- the disc, vertically centred in the safe box
    disc = 236
    cx, cy = x0 + disc // 2, y0 + SAFE_H // 2
    d.ellipse([cx - disc // 2, cy - disc // 2, cx + disc // 2, cy + disc // 2], fill=TEAL)
    f_pe = ImageFont.truetype(str(BOLD), 132)
    d.text((cx, cy - 6), "Pe", font=f_pe, fill=WHITE, anchor="mm")

    # --- wordmark and taglines, left-aligned off the disc
    tx = cx + disc // 2 + 56
    avail = (x0 + SAFE_W) - tx

    TAG = "Massively parallel physics — GPU · multicore · MPI"
    SUB = "CFD · DEM · VoF · Voronoi     pip install peclet"
    f_title = fitted(BOLD, "Péclet", 132, avail)
    f_tag = fitted(REG, TAG, 56, avail)
    f_sub = fitted(REG, SUB, 40, avail)

    d.text((tx, cy - 92), "Péclet", font=f_title, fill=WHITE, anchor="lm")
    d.text((tx, cy + 14), TAG, font=f_tag, fill=WHITE, anchor="lm")
    d.text((tx, cy + 86), SUB, font=f_sub, fill=GREY, anchor="lm")
    for f, t in ((f_title, "Péclet"), (f_tag, TAG), (f_sub, SUB)):
        assert tx + f.getbbox(t)[2] <= x0 + SAFE_W, "text escapes the TV-safe box"

    # a hairline marking the safe box is useful while designing; never in the artwork
    if "--guides" in sys.argv:
        d.rectangle([x0, y0, x0 + SAFE_W, y0 + SAFE_H], outline=(255, 0, 0))
        d.rectangle([0, (H - 423) // 2, W, (H + 423) // 2], outline=(255, 160, 0))

    img.save(out, optimize=True)
    print(f"wrote {out}  {img.size[0]}x{img.size[1]}  {out.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
