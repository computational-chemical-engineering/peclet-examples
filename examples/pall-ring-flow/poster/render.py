"""Blender scene for the Pall-ring bed poster.  blender -b -P render.py -- <style> <out.png> [res_x res_y samples]

Data (made outside Blender): bed_mesh.npz (per-ring clipped meshes, flow-domain coords, D = 1),
streams.npz (streamline polylines + speed). Sim (x, y_up, z) -> Blender (x - L/2, -(z - L/2), y).
"""
import sys, math, json
import numpy as np
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
STYLE, OUT = argv[0], argv[1]
RX, RY, SPP = (int(argv[2]), int(argv[3]), int(argv[4])) if len(argv) > 4 else (900, 1350, 128)
import os
HERE = os.getcwd() + "/"                      # data directory: run Blender from poster/data
PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pall-ring-packing", "pall_ring_pack.npz")
L = float(np.load(PACK)["box"][0]); BED = None
STR = np.load(HERE + (argv[5] if len(argv) > 5 else "streams.npz"))
Y0 = 0.0                                      # sim y of the Blender ground

def to_bl(P):
    P = np.asarray(P, float)
    return np.stack([P[:, 0] - L / 2, -(P[:, 2] - L / 2), P[:, 1] - Y0], 1)

def hexrgb(h, a=1.0):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (a,)

# ---------------------------------------------------------------------------------- styles
CERAMIC = ["#d8c3a5", "#c4785b", "#8aa1ad", "#a9b79c", "#ece6da", "#5f7488", "#d9a65b"]
INK_WARM = [(0.0, "#141e3a"), (0.3, "#1f5c8f"), (0.55, "#2fa3c4"), (0.75, "#bfe6e8"), (0.88, "#f4b26b"), (1.0, "#e2572f")]
INK = [(0.0, "#141e3a"), (0.4, "#1f5c8f"), (0.75, "#2fa3c4"), (1.0, "#a8ecef")]
MAGMA = [(0.0, "#3b0f70"), (0.35, "#b5367a"), (0.65, "#fb8761"), (1.0, "#fcfdbf")]
PLASMA = [(0.0, "#0d0887"), (0.3, "#7e03a8"), (0.6, "#cc4778"), (0.85, "#f89540"), (1.0, "#f0f921")]
STYLES = {
    "porcelain": dict(bg="light", ring="ceramic", palette=CERAMIC, lines="tubes", ramp=INK,
                      emit=0.0, radius=0.013, nlines=150, glow=0.0, cut=False, floor=True),
    "porcelain_cut": dict(bg="light", ring="ceramic", palette=CERAMIC, lines="tubes", ramp=INK,
                          emit=0.0, radius=0.012, nlines=240, glow=0.0, cut=True, floor=True),
    "nocturne_cut": dict(bg="dark", ring="gloss", palette=["#2a3442", "#3b2a35", "#2b3a33", "#33314a", "#463a2c", "#27404a", "#3a3d44"],
                         lines="tubes", ramp=MAGMA, emit=1.4, radius=0.0075, nlines=300, glow=0.35, cut=True, floor=False),
    "ceramic_whole": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK,
                          emit=0.0, radius=0.013, nlines=130, glow=0.0, cut=False, floor=True, whole=True),
    "ceramic_cut": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK,
                        emit=0.0, radius=0.012, nlines=220, glow=0.0, cut=False, floor=True, whole=True, region="square_cut"),
    "ceramic_cyl_cut": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK,
                            emit=0.0, radius=0.012, nlines=220, glow=0.0, cut=False, floor=True, whole=True, region="cyl_cut"),
    "ceramic_full": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK,
                         emit=0.0, radius=0.012, nlines=230, glow=0.0, cut=False, floor=True, whole=True, region="square_full"),
    "poster": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK_WARM,
                   emit=0.0, radius=0.009, nlines=520, glow=0.0, cut=False, floor=False, whole=True, region="square_full", cam="tall"),
    "ceramic_cyl": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK,
                        emit=0.0, radius=0.013, nlines=130, glow=0.0, cut=False, floor=True, whole=True, region="cyl"),
    "ceramic_whole_macro": dict(bg="light", ring="ceramic", palette=["#dccdb2"], lines="tubes", ramp=INK,
                                emit=0.0, radius=0.011, nlines=260, glow=0.0, cut=False, floor=False, whole=True, cam="macro"),
    "porcelain_macro": dict(bg="light", ring="ceramic", palette=CERAMIC, lines="tubes", ramp=INK,
                            emit=0.0, radius=0.011, nlines=260, glow=0.0, cut=True, floor=False, cam="macro"),
    "glass": dict(bg="dusk", ring="glass", palette=["#bfe3f5", "#e3c9f2", "#c4f0d5", "#f5e2bd", "#cfd8f7"],
                  lines="tubes", ramp=PLASMA, emit=1.0, radius=0.010, nlines=160, glow=0.3, cut=False, floor=False),
    "streaks": dict(bg="light", ring="ghost", palette=["#e07a5f", "#3d405b", "#81b29a", "#f2cc8f", "#5e8c9e", "#b56576", "#9a8c98"],
                    lines="streaks", ramp=[(0.0, "#264653"), (0.4, "#2a9d8f"), (0.7, "#e9c46a"), (1.0, "#e76f51")],
                    emit=0.0, radius=0.017, nlines=500, glow=0.0, cut=False, floor=True),
}
S = STYLES[STYLE]
if not S.get("whole"): BED = np.load(HERE + ("bed_mesh_cut.npz" if S["cut"] else "bed_mesh.npz"))   # clipped styles only

# ---------------------------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for d in prefs.devices: d.use = d.type == "OPTIX"
sc.render.engine = "CYCLES"; sc.cycles.device = "GPU"
sc.cycles.samples = SPP; sc.cycles.use_denoising = True; sc.cycles.denoiser = "OPTIX"
sc.cycles.max_bounces = 12; sc.cycles.transmission_bounces = 12; sc.cycles.glossy_bounces = 6
sc.render.resolution_x, sc.render.resolution_y = RX, RY
sc.render.film_transparent = True
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
sc.render.image_settings.color_depth = "8"

def mesh_obj(name, V, F, mat=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V)); me.vertices.foreach_set("co", np.ascontiguousarray(V, np.float32).ravel())
    me.loops.add(3 * len(F)); me.loops.foreach_set("vertex_index", np.ascontiguousarray(F, np.int32).ravel())
    me.polygons.add(len(F)); me.polygons.foreach_set("loop_start", np.arange(0, 3 * len(F), 3, dtype=np.int32))
    me.update(); me.validate()
    if smooth: me.shade_smooth()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    if mat: me.materials.append(mat)
    return ob

# ---------------------------------------------------------------------------------- ring materials
def ring_material(name, col, kind, rng):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = hexrgb(col)
    if kind == "ceramic":
        tx = nt.nodes.new("ShaderNodeTexNoise"); tx.inputs["Scale"].default_value = 180.0; tx.inputs["Detail"].default_value = 6.0
        bu = nt.nodes.new("ShaderNodeBump"); bu.inputs["Strength"].default_value = 0.06; bu.inputs["Distance"].default_value = 0.002
        nt.links.new(tx.outputs["Fac"], bu.inputs["Height"]); nt.links.new(bu.outputs["Normal"], b.inputs["Normal"])
        b.inputs["Roughness"].default_value = 0.42
        b.inputs["Coat Weight"].default_value = 0.25; b.inputs["Coat Roughness"].default_value = 0.15
        b.inputs["Subsurface Weight"].default_value = 0.08
        b.inputs["Subsurface Radius"].default_value = (0.02, 0.015, 0.01)
    elif kind == "gloss":
        b.inputs["Roughness"].default_value = 0.28
        b.inputs["Coat Weight"].default_value = 0.8; b.inputs["Coat Roughness"].default_value = 0.05
    elif kind == "matte":
        b.inputs["Roughness"].default_value = 0.6
        b.inputs["Coat Weight"].default_value = 0.1
    elif kind == "ghost":
        b.inputs["Roughness"].default_value = 0.5; b.inputs["Alpha"].default_value = 0.35
    elif kind == "glass":
        b.inputs["Transmission Weight"].default_value = 1.0; b.inputs["Roughness"].default_value = 0.04
        b.inputs["IOR"].default_value = 1.5
    return m

rng = np.random.default_rng(3)
mats = [ring_material("ring%d" % i, c, S["ring"], rng) for i, c in enumerate(S["palette"])]
nring = len(np.load(PACK)["positions"]) if BED is None else 1 + max(int(k.split("_")[1]) for k in BED.files if k.startswith("v_"))
ring_col = rng.permutation(np.arange(nring) % len(mats))
if S.get("whole"):
    from mathutils import Matrix
    RM = np.load(HERE + "ring_mesh.npz")
    proto = mesh_obj("ring_proto", RM["V"], RM["F"][:, ::-1], mats[0]); proto_me = proto.data
    bpy.data.objects.remove(proto)
    PK = np.load(PACK)
    pos = PK["positions"].astype(float); pos[:, 1] += float(STR["yshift"])
    A = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)             # sim -> Blender axes
    REG = S.get("region", "square"); RSEL = 1.95; MARG = 0.45
    def in_region(xz, m=0.0):                                       # xz (..., 2) in sim coords
        if REG.startswith("cyl"): ok = np.hypot(xz[..., 0] - L / 2, xz[..., 1] - L / 2) < RSEL - m
        else: ok = ((xz >= m) & (xz < L - m)).all(-1)
        if REG.endswith("_cut"):                                    # camera-facing quadrant removed
            ok &= ~((xz[..., 0] < L / 2) & (xz[..., 1] > L / 2))
        return ok
    shown = 0; shown_c = []
    for k, ix, iz in [(k, ix, iz) for k in range(len(pos)) for ix in (-1, 0, 1) for iz in (-1, 0, 1)]:
        c = pos[k] + [ix * L, 0, iz * L]
        if not in_region(c[[0, 2]]): continue
        shown += 1
        x, y, zq, w = PK["quaternions"][k].astype(float); nq = math.sqrt(x*x + y*y + zq*zq + w*w); x, y, zq, w = x/nq, y/nq, zq/nq, w/nq
        R = np.array([[1-2*(y*y+zq*zq), 2*(x*y-zq*w), 2*(x*zq+y*w)], [2*(x*y+zq*w), 1-2*(x*x+zq*zq), 2*(y*zq-x*w)],
                      [2*(x*zq-y*w), 2*(y*zq+x*w), 1-2*(x*x+y*y)]])
        M = np.eye(4); M[:3, :3] = A @ R; M[:3, 3] = to_bl(c[None])[0]
        ob = bpy.data.objects.new("ring%d_%d_%d" % (k, ix, iz), proto_me); sc.collection.objects.link(ob)
        ob.matrix_world = Matrix(M.tolist()); shown_c.append(c)
else:
    for k in BED.files:
        if not k.startswith("v_"): continue
        tag = k[2:]; ri = int(tag.split("_")[0])
        mesh_obj("ring_" + tag, to_bl(BED["v_" + tag]), BED["f_" + tag][:, ::-1], mats[ring_col[ri]])
        # marching cubes in (x,y,z) then a proper rotation keeps orientation; the [:, ::-1] makes normals outward

# ---------------------------------------------------------------------------------- streamlines
P_all, S_all, off = STR["P"], STR["S"], STR["off"]; Umean = float(STR["Umean"])
YLO, YHI = 0.55, float(STR["Ly"]) - 0.55
if "yshift" in STR.files and float(STR["yshift"]) > 0:      # bed spans -0.0271..5.9811 in pack coords
    YLO = -0.0271 + float(STR["yshift"]) - 1.5; YHI = 5.9811 + float(STR["yshift"]) + 1.0
lines = []
def continuous(i):
    Q = P_all[off[i]:off[i + 1]]; Q = Q[(Q[:, 1] > YLO) & (Q[:, 1] < YHI)]
    return bool(((Q[:, [0, 2]] > 0.02) & (Q[:, [0, 2]] < L - 0.02)).all())
cand = np.array([i for i in np.nonzero(STR["reached"])[0] if (S["lines"] == "streaks" or continuous(i))])
pick = set(np.random.default_rng(11).choice(cand, size=min(S["nlines"], len(cand)), replace=False).tolist())
if S.get("whole"):                     # periodic images of every line, clipped to the region's core
    segs = []
    for i in np.nonzero(STR["reached"])[0]:
        P0 = P_all[off[i]:off[i + 1]].astype(float); sp0 = S_all[off[i]:off[i + 1]].astype(float)
        keep = (P0[:, 1] > YLO) & (P0[:, 1] < YHI); P0, sp0 = P0[keep], sp0[keep]
        for ix in (-1, 0, 1):
            for iz in (-1, 0, 1):
                Pq = P0 + [ix * L, 0, iz * L]
                if not in_region(Pq[0, [0, 2]], MARG): continue        # inlet point inside the core
                ins = in_region(Pq[:, [0, 2]], MARG)
                end = len(ins) if ins.all() else int(np.argmin(ins))     # until it first leaves the core
                if end >= 6: segs.append((Pq[:end], sp0[:end]))
    if REG == "square_full":            # lines over the whole ragged heap: inside the cell OR inside a shown ring's ball
        C = np.asarray(shown_c); segs = []
        for i in np.nonzero(STR["reached"])[0]:
            P0 = P_all[off[i]:off[i + 1]].astype(float); sp0 = S_all[off[i]:off[i + 1]].astype(float)
            keep = (P0[:, 1] > YLO) & (P0[:, 1] < YHI); P0, sp0 = P0[keep], sp0[keep]
            for ix in (-1, 0, 1):
                for iz in (-1, 0, 1):
                    Pq = P0 + [ix * L, 0, iz * L]
                    if not (-0.6 < Pq[0, 0] < L + 0.6 and -0.6 < Pq[0, 2] < L + 0.6): continue
                    ins = ((Pq[:, [0, 2]] >= 0) & (Pq[:, [0, 2]] < L)).all(1)
                    out = np.nonzero(~ins)[0]
                    if len(out):
                        d2 = ((Pq[out, None, :] - C[None]) ** 2).sum(-1).min(1)
                        ins[out] = d2 < 0.72 ** 2
                    brk = np.nonzero(np.diff(ins.astype(int)) != 0)[0] + 1
                    for a, b in zip(np.r_[0, brk], np.r_[brk, len(ins)]):
                        if ins[a] and (b - a >= 60 or (a == 0 and b - a >= 12)): segs.append((Pq[a:b], sp0[a:b]))
        # pick by inlet: segments that start at the bottom are whole lines; keep their density uniform
        whole_l = [j for j, (q, _) in enumerate(segs) if q[0, 1] < YLO + 0.05]
        rng_l = np.random.default_rng(11); sel = set(rng_l.permutation(whole_l)[:S["nlines"]].tolist())
        # partial segments (re-entering at the fringe) kept at the same sampling fraction
        frac = len(sel) / max(len(whole_l), 1)
        sel |= {j for j in range(len(segs)) if j not in set(whole_l) and rng_l.random() < frac}
        pr = sorted(sel)
    else:
        pr = np.random.default_rng(11).permutation(len(segs))[:S["nlines"]]
    lines = [segs[j] for j in pr]
    print("rings shown %d, candidate lines %d" % (shown, len(segs)))
for i in ([] if S.get("whole") else range(len(off) - 1)):
    if i not in pick: continue
    P = P_all[off[i]:off[i + 1]].astype(float); sp = S_all[off[i]:off[i + 1]].astype(float)
    if len(P) < 4 or not bool(STR["reached"][i]): continue
    keep = (P[:, 1] > YLO) & (P[:, 1] < YHI); P, sp = P[keep], sp[keep]
    W = P.copy(); W[:, 0] %= L; W[:, 2] %= L                           # wrap into the periodic cell
    brk = np.abs(np.diff(W[:, [0, 2]], axis=0)).max(1) > 0.5 * L
    if S["cut"]:                                                        # drop the removed quadrant
        inq = (W[:, 0] < L / 2) & (W[:, 2] > L / 2); W[inq] = np.nan
        brk |= np.isnan(W[1:, 0]) != np.isnan(W[:-1, 0])
    jump = np.nonzero(brk)[0]
    for seg_P, seg_s in zip(np.split(W, jump + 1), np.split(sp, jump + 1)):
        if len(seg_P) >= 6 and not np.isnan(seg_P[0, 0]): lines.append((seg_P, seg_s))

def tube(P, r, attr, nside=8):
    """Tube mesh along polyline P (n,3) with per-point radius r (n,) and attribute attr (n,)."""
    n = len(P); T = np.gradient(P, axis=0); T /= np.maximum(np.linalg.norm(T, axis=1), 1e-12)[:, None]
    N = np.zeros_like(P); a = np.cross(T[0], [0.3, 0.5, 0.81]); N[0] = a / np.linalg.norm(a)
    for i in range(1, n):                                           # parallel transport
        v = N[i - 1] - np.dot(N[i - 1], T[i]) * T[i]; nv = np.linalg.norm(v)
        N[i] = v / nv if nv > 1e-9 else N[i - 1]
    B = np.cross(T, N); th = 2 * np.pi * np.arange(nside) / nside
    V = P[:, None, :] + r[:, None, None] * (np.cos(th)[None, :, None] * N[:, None, :] + np.sin(th)[None, :, None] * B[:, None, :])
    i0 = np.arange(n - 1)[:, None] * nside; j = np.arange(nside)[None, :]; j1 = (j + 1) % nside
    q = np.stack([i0 + j, i0 + j1, i0 + nside + j1, i0 + nside + j], -1).reshape(-1, 4)
    F = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
    return V.reshape(-1, 3), F, np.repeat(attr, nside)

def streaks(P, sp, rng):
    """Pathline segments: heads at random times, each covering a fixed time window (length ~ speed)."""
    ds = np.linalg.norm(np.diff(P, axis=0), axis=1); spm = 0.5 * (sp[1:] + sp[:-1])
    t = np.r_[0, np.cumsum(ds / np.maximum(spm, 0.02 * Umean))]
    TAU = 2.4 / Umean                                              # window: 1.6 D at the mean speed
    out = []; th = rng.uniform(0, 1.3 * TAU)
    while th < t[-1]:
        sel = (t >= th - TAU) & (t <= th)
        if sel.sum() >= 4: out.append((P[sel], sp[sel], (t[sel] - (th - TAU)) / TAU))
        th += rng.uniform(1.2, 2.4) * TAU
    return out

srng = np.random.default_rng(7)
VV, FF, AA, nv = [], [], [], 0
for P, sp in lines:
    Pb = to_bl(P)
    if S["lines"] == "tubes":
        r = np.full(len(Pb), S["radius"]); taper = np.minimum(1, np.minimum(np.arange(len(Pb)), np.arange(len(Pb))[::-1]) / 6)
        V, F, A = tube(Pb, r * (0.3 + 0.7 * taper), sp / Umean)
        VV.append(V); FF.append(F + nv); AA.append(A); nv += len(V)
    else:
        for Q, sq, f in streaks(Pb, sp, srng):
            r = S["radius"] * np.sqrt(np.clip(f, 0, 1)) * np.minimum(1, (1 - f) * 25 + 0.35)
            V, F, A = tube(Q, np.maximum(r, 1e-4), sq / Umean)
            VV.append(V); FF.append(F + nv); AA.append(A); nv += len(V)
V, F, A = np.concatenate(VV), np.concatenate(FF), np.concatenate(AA)
ob = mesh_obj("streamlines", V, F)
at = ob.data.attributes.new("speed", "FLOAT", "POINT"); at.data.foreach_set("value", A.astype(np.float32))
m = bpy.data.materials.new("lines"); m.use_nodes = True; nt = m.node_tree; b = nt.nodes["Principled BSDF"]
an = nt.nodes.new("ShaderNodeAttribute"); an.attribute_name = "speed"
mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.0; mr.inputs["From Max"].default_value = 3.0
cr = nt.nodes.new("ShaderNodeValToRGB"); el = cr.color_ramp.elements
for i, (pos, col) in enumerate(S["ramp"]):
    e = el[i] if i < 2 else el.new(pos); e.position = pos; e.color = hexrgb(col)
nt.links.new(an.outputs["Fac"], mr.inputs["Value"]); nt.links.new(mr.outputs["Result"], cr.inputs["Fac"])
nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
b.inputs["Roughness"].default_value = 0.35; b.inputs["Coat Weight"].default_value = 0.3
if S["emit"] > 0:
    nt.links.new(cr.outputs["Color"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = S["emit"]
ob.data.materials.append(m)
print("streamline segments %d, tube verts %d" % (len(lines), len(V)))

# ---------------------------------------------------------------------------------- frame (thin cell edges)
H = float(STR["Ly"])
# (kept out by default; uncomment to draw the periodic cell)

# ---------------------------------------------------------------------------------- lights, world, floor
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
bgn = world.node_tree.nodes["Background"]
if S["bg"] == "light":
    bgn.inputs["Color"].default_value = hexrgb("#f4f1ec"); bgn.inputs["Strength"].default_value = 0.55
elif S["bg"] == "dark":
    bgn.inputs["Color"].default_value = hexrgb("#10131a"); bgn.inputs["Strength"].default_value = 0.25
else:
    bgn.inputs["Color"].default_value = hexrgb("#2b3550"); bgn.inputs["Strength"].default_value = 0.5

def area(name, loc, size, energy, col="#ffffff", target=(0, 0, 3.2)):
    ld = bpy.data.lights.new(name, "AREA"); ld.size = size; ld.energy = energy; ld.color = hexrgb(col)[:3]
    lo = bpy.data.objects.new(name, ld); sc.collection.objects.link(lo); lo.location = loc
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return lo
K = {"light": 1.0, "dark": 0.8, "dusk": 0.9}[S["bg"]]
area("key", (-7, -6, 10), 6.0, 2600 * K, "#fff4e6")
area("fill", (9, -4, 4), 8.0, 700 * K, "#e6f0ff")
area("rim", (2, 9, 9), 4.0, 1800 * K, "#ffffff")
floor = mesh_obj("floor", np.array([[-30, -30, 0], [30, -30, 0], [30, 30, 0], [-30, 30, 0]], float) + [0, 0, YLO - 0.02],
                 np.array([[0, 1, 2], [0, 2, 3]]), smooth=False)
floor.is_shadow_catcher = True
if not S["floor"]: bpy.data.objects.remove(floor)

# ---------------------------------------------------------------------------------- camera
cam = bpy.data.cameras.new("cam"); cam.lens = 70; cam.sensor_width = 36
co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co
target = Vector((0, 0, 0.5 * (YLO + YHI)))
az, el, dist = math.radians(-38), math.radians(20), 21.0
if S.get("cam") == "tall":
    target = Vector((0, 0, 0.5 * (YLO + YHI))); dist = 23.5
if S.get("cam") == "macro":
    cam.lens = 45; target = Vector((-0.2, 0.2, 3.2)); az, el, dist = math.radians(-40), math.radians(12), 6.2
co.location = target + dist * Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
cam.dof.use_dof = True; cam.dof.focus_distance = (target - co.location).length - 0.6; cam.dof.aperture_fstop = 4.0 if S.get("cam") != "macro" else 1.6

# ---------------------------------------------------------------------------------- bloom for glowing styles
if S["glow"] > 0:
    sc.use_nodes = True; ct = sc.node_tree
    rl = ct.nodes["Render Layers"]; comp = ct.nodes["Composite"]
    g = ct.nodes.new("CompositorNodeGlare"); g.glare_type = "BLOOM"
    try:
        g.inputs["Strength"].default_value = S["glow"]
    except Exception:
        g.mix = S["glow"] - 1.0
    ct.links.new(rl.outputs["Image"], g.inputs["Image"]); ct.links.new(g.outputs["Image"], comp.inputs["Image"])

sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("WROTE", OUT)
