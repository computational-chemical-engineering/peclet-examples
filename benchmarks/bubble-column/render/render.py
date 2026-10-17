"""Blender scene of the bubble column.  blender -b -P render.py -- <mesh.npz> <out.png> [rx ry spp style device]

mesh.npz from bubbles_mesh.py (D = 1 units, solver frame: x vertical with + = DOWN, y wall-normal
with the no-slip walls at y = 0 and y = LY, z spanwise; x and z periodic). Blender frame (right-
handed, z up, column centred on the origin):  X = y - LY/2,  Y = -(z - LZ/2),  Z = LX - x.

Styles: "glass" (clear, slightly tinted bubbles), "pearl" (glassy with a milky body), "solid"
(soft satin bubbles); all draw the two walls as faint panes with thin edges and, behind the
column, a panel of the depth-averaged vertical liquid velocity (blue = down, warm = up); a style
"<name>_nopanel" drops the panel. device: "gpu" (OptiX) or "cpu" (16 threads). The background is
transparent; glass refracts the neutral world, so a bubble never shows the page colour through it
(the image reads on the light and the dark site theme).
"""
import math
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
MESH, OUT = argv[0], argv[1]
RX, RY, SPP = (int(argv[2]), int(argv[3]), int(argv[4])) if len(argv) > 4 else (600, 800, 64)
STYLE = argv[5] if len(argv) > 5 else "glass"
DEVICE = argv[6] if len(argv) > 6 else "gpu"
PANEL = not STYLE.endswith("_nopanel")
STYLE = STYLE.replace("_nopanel", "")
Z = np.load(MESH)
LX, LY, LZ = (float(v) for v in Z["L"])


def to_bl(P):
    P = np.asarray(P, float)
    return np.stack([P[:, 1] - LY / 2, -(P[:, 2] - LZ / 2), LX - P[:, 0]], 1)


def hexrgb(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (a,)


# ------------------------------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
if DEVICE == "gpu":
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    sc.cycles.device = "GPU"
    sc.cycles.denoiser = "OPTIX"
else:
    sc.cycles.device = "CPU"
    sc.render.threads_mode = "FIXED"
    sc.render.threads = 16
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.samples = SPP
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 16
sc.cycles.transmission_bounces = 16
sc.cycles.glossy_bounces = 6
sc.cycles.transparent_max_bounces = 16
sc.render.resolution_x, sc.render.resolution_y = RX, RY
sc.render.film_transparent = True
sc.cycles.film_transparent_glass = False         # glass shows the neutral world, never the page
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.render.image_settings.color_depth = "8"


def mesh_obj(name, V, F, mat=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", np.ascontiguousarray(V, np.float32).ravel())
    me.loops.add(3 * len(F))
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(F, np.int32).ravel())
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", np.arange(0, 3 * len(F), 3, dtype=np.int32))
    me.update()
    me.validate()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def principled(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes["Principled BSDF"]


# ------------------------------------------------------------------------------------- bubbles
if STYLE == "glass":
    mb, nt, b = principled("bubble")
    b.inputs["Base Color"].default_value = hexrgb("#e4f3fb")
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.0
    b.inputs["IOR"].default_value = 1.33
    b.inputs["Coat Weight"].default_value = 0.3
    b.inputs["Coat Roughness"].default_value = 0.02
elif STYLE == "pearl":                                   # glassy, but with a milky body that
    mb, nt, b = principled("bubble")                     # does not go dark over a dark page
    b.inputs["Base Color"].default_value = hexrgb("#eef6fa")
    b.inputs["Transmission Weight"].default_value = 0.7
    b.inputs["Roughness"].default_value = 0.04
    b.inputs["IOR"].default_value = 1.33
    b.inputs["Coat Weight"].default_value = 0.5
    b.inputs["Coat Roughness"].default_value = 0.03
else:
    mb, nt, b = principled("bubble")
    b.inputs["Base Color"].default_value = hexrgb("#bcd9ea")
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Coat Weight"].default_value = 0.6
    b.inputs["Coat Roughness"].default_value = 0.08
    b.inputs["Subsurface Weight"].default_value = 0.15
    b.inputs["Subsurface Radius"].default_value = (0.2, 0.25, 0.3)
for k in range(int(Z["nblocks"])):
    ob = mesh_obj(f"bubble{k}", to_bl(Z[f"V{k}"]), Z[f"F{k}"], mb)
    sub = ob.modifiers.new("sub", "SUBSURF")
    sub.levels = sub.render_levels = 2

# ------------------------------------------------------------------------------------- walls
mw, nt, b = principled("wall")
b.inputs["Base Color"].default_value = hexrgb("#dfe7ec")
b.inputs["Roughness"].default_value = 0.15
b.inputs["Alpha"].default_value = 0.06
me, nte, be = principled("edge")
be.inputs["Base Color"].default_value = hexrgb("#6f7a86")       # mid-grey: reads on light and dark pages
be.inputs["Roughness"].default_value = 0.5
TH, ER = 0.03, 0.022                                  # pane thickness, edge-rod radius (D)


def box(name, lo, hi, mat):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    V = np.array([[lo[0] if i & 1 == 0 else hi[0], lo[1] if i & 2 == 0 else hi[1],
                   lo[2] if i & 4 == 0 else hi[2]] for i in range(8)])
    F = np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                  [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]])
    return mesh_obj(name, V, F, mat, smooth=False)


def rod(name, a, b_, r, mat):
    a, b_ = Vector(a), Vector(b_)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=r, depth=(b_ - a).length,
                                        location=(a + b_) / 2)
    ob = bpy.context.active_object
    ob.name = name
    ob.rotation_euler = (b_ - a).to_track_quat("Z", "Y").to_euler()
    ob.data.materials.append(mat)
    return ob


for s, xw in (("lo", -LY / 2 - TH), ("hi", LY / 2)):
    box(f"wall_{s}", (xw, -LZ / 2, 0.0), (xw + TH, LZ / 2, LX), mw)
    xe = xw if s == "lo" else xw + TH                    # outer face edges
    for (ya, za), (yb, zb) in (((-LZ / 2, 0), (LZ / 2, 0)), ((-LZ / 2, LX), (LZ / 2, LX)),
                               ((-LZ / 2, 0), (-LZ / 2, LX)), ((LZ / 2, 0), (LZ / 2, LX))):
        rod(f"edge_{s}_{ya}_{za}_{zb}", (xe, ya, za), (xe, yb, zb), ER, me)

# ------------------------------------------------------------------------------------- velocity panel
if PANEL:
    U = np.asarray(Z["ul_xy"], float)                   # (NX, NY), + = down
    nx, ny = U.shape
    h = float(Z["h"])
    # vertices on cell centres, plus the wall values (no slip: 0) at y = 0 and y = LY
    ys = np.r_[0.0, (np.arange(ny) + 0.5) * h, LY]
    Uw = np.concatenate([np.zeros((nx, 1)), U, np.zeros((nx, 1))], axis=1)
    xs = (np.arange(nx) + 0.5) * h                       # periodic in x: close with the first row
    xs = np.r_[xs, xs[0] + LX]
    Uw = np.concatenate([Uw, Uw[:1]], axis=0)
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    P = np.stack([XX.ravel(), YY.ravel(), np.full(XX.size, 0.0)], 1)
    Vb = to_bl(P)
    Vb[:, 1] = LZ / 2 + 0.06                             # just behind the column's back face
    Vb[:, 2] = np.clip(Vb[:, 2], 0.0, LX)
    nyy = len(ys)
    q = (np.arange(nx)[:, None] * nyy + np.arange(nyy - 1)[None, :]).ravel()
    F = np.concatenate([np.stack([q, q + 1, q + nyy + 1], 1), np.stack([q, q + nyy + 1, q + nyy], 1)])
    ob = mesh_obj("panel", Vb, F, smooth=True)
    at = ob.data.attributes.new("ul", "FLOAT", "POINT")
    at.data.foreach_set("value", Uw.ravel().astype(np.float32))
    mp, nt, b = principled("panel")
    an = nt.nodes.new("ShaderNodeAttribute")
    an.attribute_name = "ul"
    mr = nt.nodes.new("ShaderNodeMapRange")
    UMAX = 0.6
    mr.inputs["From Min"].default_value = -UMAX
    mr.inputs["From Max"].default_value = UMAX
    cr = nt.nodes.new("ShaderNodeValToRGB")
    el = cr.color_ramp.elements                         # 0 = up (warm), 1 = down (blue)
    for i, (pos, col) in enumerate([(0.0, "#c2522d"), (0.3, "#eba77d"), (0.5, "#f3f1ee"),
                                    (0.7, "#86b6d8"), (1.0, "#1f5c8f")]):
        e = el[i] if i < 2 else el.new(pos)
        e.position = pos
        e.color = hexrgb(col)
    nt.links.new(an.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.8
    b.inputs["Alpha"].default_value = 1.0
    ob.data.materials.append(mp)
    ob.visible_shadow = False

# ------------------------------------------------------------------------------------- world, lights
world = bpy.data.worlds.new("w")
sc.world = world
world.use_nodes = True
bgn = world.node_tree.nodes["Background"]
bgn.inputs["Color"].default_value = hexrgb("#eef0f2")
bgn.inputs["Strength"].default_value = 0.7


def area(name, loc, size, energy, col="#ffffff", target=(0, 0, LX / 2)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.size = size
    ld.energy = energy
    ld.color = hexrgb(col)[:3]
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return lo


area("key", (-9, -12, 13), 7.0, 3200, "#fff4e6")
area("fill", (11, -9, 5), 9.0, 1100, "#e6f0ff")
area("rim", (3, 10, 12), 5.0, 1400)

# ------------------------------------------------------------------------------------- camera
cam = bpy.data.cameras.new("cam")
cam.lens = 85
cam.sensor_width = 36
cam.sensor_fit = "VERTICAL"
cam.sensor_height = 24
co = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(co)
sc.camera = co
target = Vector((0.0, 0.0, LX / 2 - 0.05))
az, elv, dist = math.radians(-22), math.radians(9), 37.0
co.location = target + dist * Vector((math.sin(az) * math.cos(elv), -math.cos(az) * math.cos(elv),
                                      math.sin(elv)))
co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()

sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("WROTE", OUT)
