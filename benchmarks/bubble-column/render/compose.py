#!/usr/bin/env python3
"""Add the velocity-panel colour bar under a render.py image, and make the web PNG.

    python compose.py <render.png> <out.png> [--width 1600] [--colours 256] [--check]

The colour bar matches render.py's panel ramp (UMAX = 0.6, + = down) and uses a mid-grey ink that
reads on both the light and the dark site theme; the background stays transparent. The output is
resized to `--width` px on its long side (Lanczos) and saved optimised; --colours N quantises it to
an N-colour RGBA palette PNG with libimagequant (the pngquant library; `pip install imagequant`,
dithered), which keeps the web figure under 1 MB without visible banding. PIL's own quantisers band
the smooth velocity panel, so without imagequant the image stays truecolour (and too large). --check also writes
<out>_on_light.png / <out>_on_dark.png, the image flattened onto the two site backgrounds.
"""
import io
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from PIL import Image  # noqa: E402

UMAX = 0.6
RAMP = [(0.0, "#c2522d"), (0.3, "#eba77d"), (0.5, "#f3f1ee"), (0.7, "#86b6d8"), (1.0, "#1f5c8f")]
INK = "#8a8f96"


def colourbar(width_px):
    dpi = 200 * max(1.0, width_px / 1150)                     # same look at any image width
    cm = LinearSegmentedColormap.from_list("panel", RAMP)
    w_in = width_px / dpi
    fig = plt.figure(figsize=(w_in, w_in * 0.13), dpi=dpi)
    ax = fig.add_axes([0.2, 0.55, 0.6, 0.18])
    ax.imshow(np.linspace(-UMAX, UMAX, 256)[None, :], aspect="auto", cmap=cm,
              extent=(-UMAX, UMAX, 0, 1))
    ax.set_yticks([])
    ax.set_xticks([-UMAX, -0.3, 0, 0.3, UMAX])
    ax.tick_params(colors=INK, labelsize=7, length=2)
    for s in ax.spines.values():
        s.set_edgecolor(INK)
        s.set_linewidth(0.6)
    ax.set_xlabel(r"depth-averaged liquid velocity along the column $/\sqrt{gD}$", color=INK,
                  fontsize=7, labelpad=2)
    for x, txt, ha in ((-UMAX, "up  ", "right"), (UMAX, "  down", "left")):
        ax.text(x, 0.5, txt, color=INK, fontsize=7, ha=ha, va="center")
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def trim_box(im, pad):
    """Bounding box of the pixels with alpha > 2/255, grown by `pad`."""
    a = np.asarray(im)[..., 3] > 2
    ys, xs = np.nonzero(a.any(1))[0], np.nonzero(a.any(0))[0]
    return (max(xs[0] - pad, 0), max(ys[0] - pad, 0), min(xs[-1] + 1 + pad, im.width),
            min(ys[-1] + 1 + pad, im.height))


def main():
    src, out = sys.argv[1], sys.argv[2]
    width = int(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 1600
    colours = int(sys.argv[sys.argv.index("--colours") + 1]) if "--colours" in sys.argv else 0
    im = Image.open(src).convert("RGBA")
    im = im.crop(trim_box(im, int(0.015 * im.width)))         # trim the empty render margins
    cb = colourbar(im.width)
    cb = cb.resize((im.width, int(cb.height * im.width / cb.width)), Image.LANCZOS)
    canvas = Image.new("RGBA", (im.width, im.height + cb.height), (0, 0, 0, 0))
    canvas.paste(im, (0, 0))
    canvas.alpha_composite(cb, (0, im.height))
    canvas = canvas.crop(trim_box(canvas, int(0.015 * canvas.width)))
    s = width / max(canvas.size)
    if s < 1:
        canvas = canvas.resize((round(canvas.width * s), round(canvas.height * s)), Image.LANCZOS)
    a = np.asarray(canvas).copy()                             # alpha to 1/64 steps: the faint
    a[..., 3] = (np.round(a[..., 3] / 4.0) * 4).clip(0, 255)  # wall panes carry sampling noise
    canvas = Image.fromarray(a, "RGBA")                       # in alpha that costs ~30 % of size
    if colours:                                               # palette PNG: the web size cap
        try:
            import imagequant
            canvas = imagequant.quantize_pil_image(canvas, dithering_level=1.0,
                                                   max_colors=colours)
        except ImportError:
            print("imagequant not installed: writing truecolour")
    canvas.save(out, optimize=True)
    print(f"wrote {out}: {canvas.width}x{canvas.height}")
    if "--check" in sys.argv:
        for name, bg in (("light", "#ffffff"), ("dark", "#222428")):
            flat = Image.new("RGBA", canvas.size, bg)
            flat.alpha_composite(canvas.convert("RGBA"))
            flat.convert("RGB").save(out.replace(".png", f"_on_{name}.png"))


if __name__ == "__main__":
    main()
