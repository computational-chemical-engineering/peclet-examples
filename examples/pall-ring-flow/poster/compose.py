"""Composite a transparent render over a poster background.  compose.py in.png out.png light|dark|dusk"""
import sys, numpy as np
from PIL import Image
im = np.asarray(Image.open(sys.argv[1]).convert("RGBA")).astype(float) / 255
H, W = im.shape[:2]; y, x = np.mgrid[0:H, 0:W]; y = y / H; x = x / W
r = np.sqrt((x - 0.5) ** 2 + ((y - 0.45) * H / W) ** 2)
def c(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255
kind = sys.argv[3]
if kind == "white":
    bg = np.ones((H, W, 3))
elif kind == "light":
    bg = c("#fbf9f5")[None, None] * (1 - y[..., None]) + c("#e7e2da")[None, None] * y[..., None]
    bg *= (1 - 0.10 * np.clip(r - 0.35, 0, 1))[..., None]
elif kind == "dark":
    t = np.clip(r / 0.85, 0, 1)[..., None]; bg = c("#1d2636") * (1 - t) + c("#06080c") * t
else:
    t = np.clip(r / 0.9, 0, 1)[..., None]; bg = c("#3a4a6e") * (1 - t) + c("#0e1220") * t
a = im[..., 3:4]
out = im[..., :3] + bg * (1 - a)          # Blender writes straight alpha for PNG -> premultiply
out = im[..., :3] * a + bg * (1 - a)
Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(sys.argv[2])
