"""Film thickness between two bubbles along their line of centres (all lengths in D)."""
import numpy as np
from scipy.ndimage import map_coordinates


def profile(arr, lo, x0, x1, S, N, periodic=(True, False, True), n=801):
    s = np.linspace(0.0, 1.0, n)
    p = x0[None, :] + s[:, None] * (x1 - x0)[None, :]
    q = p * S - 0.5 - np.asarray(lo, float)[None, :]
    for k in range(3):
        if periodic[k]:
            c = 0.5 * (arr.shape[k] - 1)
            q[:, k] -= N[k] * np.round((q[:, k] - c) / N[k])
    return s, map_coordinates(arr, q.T, order=1, mode="constant", cval=0.0)


def gap_markers(a1, lo1, a2, lo2, c1, c2, S, N, L):
    """Per-marker colours (gas = 1): signed gap between C1 = 1/2 leaving 1 and C2 = 1/2 entering 2."""
    c1 = np.asarray(c1, float); d = np.asarray(c2, float) - c1
    for k in (0, 2):
        d[k] -= L[k] * np.round(d[k] / L[k])
    c2 = c1 + d; dist = np.linalg.norm(d)
    s, f1 = profile(a1, lo1, c1, c2, S, N)
    _, f2 = profile(a2, lo2, c1, c2, S, N)
    i = np.argmax(f1 < 0.5)                      # first point outside bubble 1
    s1 = s[i - 1] + (s[i] - s[i - 1]) * (f1[i - 1] - 0.5) / (f1[i - 1] - f1[i])
    j = len(s) - 1 - np.argmax(f2[::-1] < 0.5)   # last point outside bubble 2
    s2 = s[j] + (s[j + 1] - s[j]) * (0.5 - f2[j]) / (f2[j + 1] - f2[j])
    return (s2 - s1) * dist


def gap_single(a, c1, c2, S, N, L):
    """One colour field: length of the C < 1/2 stretch between the centres (0 if bridged)."""
    c1 = np.asarray(c1, float); d = np.asarray(c2, float) - c1
    for k in (0, 2):
        d[k] -= L[k] * np.round(d[k] / L[k])
    c2 = c1 + d; dist = np.linalg.norm(d)
    sg = np.linspace(0.0, 1.0, 801)
    pts = c1[None, :] + sg[:, None] * (c2 - c1)[None, :]
    q = (pts * S - 0.5).T
    s, f = sg, map_coordinates(a, q, order=1, mode="grid-wrap")
    out = f < 0.5
    if not out.any():
        return 0.0
    i = np.argmax(out); j = len(s) - 1 - np.argmax(out[::-1])
    if i == 0 or j == len(s) - 1:
        return float("nan")
    s1 = s[i - 1] + (s[i] - s[i - 1]) * (f[i - 1] - 0.5) / (f[i - 1] - f[i])
    s2 = s[j] + (s[j + 1] - s[j]) * (0.5 - f[j]) / (f[j + 1] - f[j])
    return (s2 - s1) * dist
