"""
Combat Boot / Anfibio  —  Product Shot Pipeline
================================================
Scala: metri reali. Engine: BLENDER_EEVEE (Blender 5.1, no _NEXT, no Cycles).

v1 BLOCKOUT  : proporzioni confermate (loft anelli + boolean union).
v2 SHAPE     : sezioni squircle (fondo piatto, lati verticali), gambale alto
               e dritto, punta blunt/rialzata, throat anteriore aperto +
               tongue, suola spessa con tacco e lug tread.
"""

import urllib.request, json, base64, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLENDER_URL = "http://localhost:7234"
RENDER_DIR  = "D:/blender-claude/renders"


def blender(code, timeout=120):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 15)
    r    = json.loads(resp.read().decode())
    if "error" in r:
        print("ERR:", r["error"][:1500])
        return None
    return r.get("ok")


def render_save(path, w=1280, h=960, samples=64, exposure=-0.6):
    code = f"""
import bpy, base64, os, tempfile
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = {samples}
try:
    sc.eevee.use_raytracing = True
except Exception:
    pass
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = {exposure}
sc.render.use_compositing = False
tmp = tempfile.mktemp(suffix=".png"); sc.render.filepath = tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
os.remove(tmp)
result = {{"b64": b64}}
"""
    r = blender(code, timeout=240)
    if r and "b64" in r:
        img = base64.b64decode(r["b64"])
        with open(path, "wb") as f:
            f.write(img)
        print(f"  Render salvato: {path} ({len(img)//1024} KB)")
        return True
    print("  Render FALLITO")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# V2 — SHAPE REFINEMENT
# ─────────────────────────────────────────────────────────────────────────────
V2_BUILD = r"""
import bpy, bmesh, math
from mathutils import Vector

# ── Pulizia scena ────────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
            bpy.data.lights, bpy.data.curves):
    for d in list(blk):
        blk.remove(d)

N = 40  # segmenti per anello

def sq(c, h, t, e):
    # coordinata squircle: e=2 ellisse, e>2 piu' squadrato
    s = math.cos(t) if c == 'c' else math.sin(t)
    return (math.copysign(abs(s) ** (2.0 / e), s)) * h

def ring_yz(x, hy, zb, zt, e=3.2, n=N):
    # sezione del piede nel piano Y-Z (fondo piatto, lati verticali)
    cz = (zb + zt) * 0.5
    hz = (zt - zb) * 0.5
    out = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        out.append((x, sq('c', hy, t, e), cz + sq('s', hz, t, e)))
    return out

def ring_xy(z, cx, hx, hy, e=2.6, n=N):
    # sezione del gambale nel piano X-Y
    out = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        out.append((cx + sq('c', hx, t, e), sq('s', hy, t, e), z))
    return out

def build_loft(name, rings, cap_start=True, cap_end=True):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bm = bmesh.new()
    vloops = [[bm.verts.new(p) for p in r] for r in rings]
    bm.verts.ensure_lookup_table()
    n = len(rings[0])
    for a, b in zip(vloops[:-1], vloops[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new([a[i], a[j], b[j], b[i]])
    if cap_start:
        c = bm.verts.new(tuple(sum(v) / n for v in zip(*rings[0])))
        for i in range(n):
            bm.faces.new([vloops[0][(i + 1) % n], vloops[0][i], c])
    if cap_end:
        c = bm.verts.new(tuple(sum(v) / n for v in zip(*rings[-1])))
        for i in range(n):
            bm.faces.new([vloops[-1][i], vloops[-1][(i + 1) % n], c])
    bm.normal_update()
    bm.to_mesh(me); bm.free(); me.update()
    return ob

def boolean(target, cutter, op):
    bpy.context.view_layer.objects.active = target
    m = target.modifiers.new(op, 'BOOLEAN')
    m.operation = op
    m.solver = 'EXACT'
    m.object = cutter
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    target.data.validate()

# ── UPPER: piede (loft lungo X) ──────────────────────────────────────────────
# (x, half_width_y, z_bottom, z_top)  EU ~43, punta blunt + toe-spring
foot_stations = [
    (0.000, 0.035, 0.030, 0.082),  # tallone
    (0.030, 0.042, 0.022, 0.088),  # dietro collo
    (0.075, 0.045, 0.020, 0.090),  # collo del piede (instep, piu' basso)
    (0.120, 0.049, 0.018, 0.082),  # mezzo
    (0.165, 0.052, 0.017, 0.070),  # avampiede (max larghezza)
    (0.205, 0.051, 0.017, 0.058),  # dita
    (0.240, 0.046, 0.020, 0.049),  # toe box (tozzo, basso)
    (0.262, 0.036, 0.026, 0.045),  # punta (toe spring)
    (0.276, 0.021, 0.032, 0.043),  # cappello punta
]
foot_rings = [ring_yz(x, hy, zb, zt) for (x, hy, zb, zt) in foot_stations]
foot = build_loft("Boot_Foot", foot_rings)

# ── UPPER: gambale alto e dritto (loft lungo Z) ──────────────────────────────
# (z, center_x, half_len_x, half_width_y)
shaft_stations = [
    (0.060, 0.058, 0.072, 0.049),  # base (dentro al piede)
    (0.120, 0.052, 0.052, 0.049),  # caviglia
    (0.205, 0.051, 0.050, 0.049),  # tibia
    (0.300, 0.052, 0.050, 0.049),  # bocca dello stivale
]
shaft_rings = [ring_xy(z, cx, hx, hy) for (z, cx, hx, hy) in shaft_stations]
shaft = build_loft("Boot_Shaft", shaft_rings)

boolean(foot, shaft, 'UNION')
foot.name = "Boot_Upper"
upper = foot

# ── Apertura superiore (buco gamba) ──────────────────────────────────────────
bpy.ops.mesh.primitive_cylinder_add(radius=0.046, depth=0.16, vertices=44,
                                     location=(0.052, 0.0, 0.315))
boolean(upper, bpy.context.active_object, 'DIFFERENCE')

# ── Throat anteriore: canale con BASE ESPLICITA (T, Y, V=T x Y) ──────────────
# Linea condivisa instep->collare (identica in V3). Sulla superficie reale.
THROAT_P0 = Vector((0.150, 0.0, 0.082))   # instep (collo del piede)
THROAT_P1 = Vector((0.052, 0.0, 0.292))   # collare (alto)
TD   = THROAT_P1 - THROAT_P0
TLEN = TD.length
T_ax = TD.normalized()                    # asse linea (lunghezza)
U_ax = Vector((0.0, 1.0, 0.0))            # larghezza = Y mondo (gap in Y)
V_ax = T_ax.cross(U_ax).normalized()      # profondita' (dentro al boot)

def build_box(name, center, a, b, c):
    me_ = bpy.data.meshes.new(name)
    ob_ = bpy.data.objects.new(name, me_)
    bpy.context.collection.objects.link(ob_)
    bm_ = bmesh.new()
    vs = {}
    for si in (-1, 1):
        for sj in (-1, 1):
            for sk in (-1, 1):
                vs[(si, sj, sk)] = bm_.verts.new(
                    center + si * a * T_ax + sj * b * U_ax + sk * c * V_ax)
    F = [
        [(-1,-1,-1),(-1,-1, 1),(-1, 1, 1),(-1, 1,-1)],
        [( 1,-1,-1),( 1, 1,-1),( 1, 1, 1),( 1,-1, 1)],
        [(-1,-1,-1),( 1,-1,-1),( 1,-1, 1),(-1,-1, 1)],
        [(-1, 1,-1),(-1, 1, 1),( 1, 1, 1),( 1, 1,-1)],
        [(-1,-1,-1),(-1, 1,-1),( 1, 1,-1),( 1,-1,-1)],
        [(-1,-1, 1),( 1,-1, 1),( 1, 1, 1),(-1, 1, 1)],
    ]
    for f in F:
        bm_.faces.new([vs[t] for t in f])
    bm_.normal_update()
    bm_.to_mesh(me_); bm_.free(); me_.update()
    return ob_

TMID = (THROAT_P0 + THROAT_P1) * 0.5
slot = build_box("ThroatCut", TMID, TLEN * 0.5 + 0.012, 0.020, 0.016)
boolean(upper, slot, 'DIFFERENCE')

sub = upper.modifiers.new("Subsurf", 'SUBSURF')
sub.levels = 1
sub.render_levels = 2
for p in upper.data.polygons:
    p.use_smooth = True

# ── TONGUE: striscia nel canale, incassata ma visibile tra le due file ───────
NR = 20
def tongue_ring(s, hw, hth):
    ctr = THROAT_P0 + TD * s - V_ax * 0.003   # quasi a filo della superficie
    r = []
    for i in range(NR):
        t = 2.0 * math.pi * i / NR
        r.append(ctr + U_ax * sq('c', hw, t, 2.4) + V_ax * sq('s', hth, t, 2.0))
    return r
tongue_rings = [
    tongue_ring(0.02, 0.016, 0.0050),
    tongue_ring(0.32, 0.019, 0.0055),
    tongue_ring(0.64, 0.019, 0.0055),
    tongue_ring(0.97, 0.019, 0.0055),
]
me = bpy.data.meshes.new("Boot_Tongue")
tongue = bpy.data.objects.new("Boot_Tongue", me)
bpy.context.collection.objects.link(tongue)
bm = bmesh.new()
vl = [[bm.verts.new(p) for p in rr] for rr in tongue_rings]
for a, b in zip(vl[:-1], vl[1:]):
    for i in range(NR):
        j = (i + 1) % NR
        bm.faces.new([a[i], a[j], b[j], b[i]])
for cap, rev in ((vl[0], True), (vl[-1], False)):
    cc = bm.verts.new(tuple(sum(v) / NR
                            for v in zip(*[(p.co.x, p.co.y, p.co.z) for p in cap])))
    for i in range(NR):
        j = (i + 1) % NR
        f = [cap[i], cap[j], cc] if rev else [cap[j], cap[i], cc]
        bm.faces.new(f)
bm.normal_update()
bm.to_mesh(me); bm.free(); me.update()
for p in tongue.data.polygons:
    p.use_smooth = True

# ── SUOLA spessa: midsole svasata + tacco + lug tread ────────────────────────
sole_top = 0.034
me = bpy.data.meshes.new("Boot_Sole")
sole = bpy.data.objects.new("Boot_Sole", me)
bpy.context.collection.objects.link(sole)
bm = bmesh.new()
# profilo bottom: piu' basso al tacco (heel lift)
def sole_bot_z(x):
    if x < 0.085:
        return -0.014   # tacco sporge sotto
    if x < 0.120:
        return -0.014 + (x - 0.085) / 0.035 * 0.014  # raccordo
    return 0.000
prof = []
for (x, hy, zb, zt) in foot_stations:
    prof.append((x, hy + 0.012))            # svaso suola +1.2 cm
prof = [(-0.012, 0.030)] + prof              # estende dietro al tacco
prof += [(0.286, 0.014)]                     # punta suola
seq = [(x, y) for (x, y) in prof] + [(x, -y) for (x, y) in reversed(prof)]
top = [bm.verts.new((x, y, sole_top)) for (x, y) in seq]
bot = [bm.verts.new((x, y, sole_bot_z(x))) for (x, y) in seq]
bm.verts.ensure_lookup_table()
M = len(seq)
for i in range(M):
    j = (i + 1) % M
    bm.faces.new([top[i], top[j], bot[j], bot[i]])
bm.faces.new(list(reversed(top)))
bm.faces.new(bot)
bm.normal_update()
bm.to_mesh(me); bm.free(); me.update()
for p in sole.data.polygons:
    p.use_smooth = False
bev = sole.modifiers.new("Bevel", 'BEVEL')
bev.width = 0.006
bev.segments = 3
bev.limit_method = 'ANGLE'
bev.angle_limit = math.radians(40)
bpy.context.view_layer.objects.active = sole
bpy.ops.object.modifier_apply(modifier="Bevel")
# NB: lug tread (carrarmato) -> bump/normal procedurale in fase materiali (v4),
#     NON geometria booleana (fragile, distrugge la suola).

# ── WELT (rand) + STITCH (cucitura Goodyear) lungo la giuntura suola/upper ────
cxw = sum(x for x, y in seq) / len(seq)
cyw = sum(y for x, y in seq) / len(seq)

def closed_curve(name, pts, bevel, res):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = bevel
    cu.bevel_resolution = res
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    sp.use_cyclic_u = True
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    return ob

welt_pts = [(x + (x - cxw) * 0.05, y + (y - cyw) * 0.16, sole_top + 0.004)
            for (x, y) in seq]
welt = closed_curve("Boot_Welt", welt_pts, 0.0070, 3)

stitch_pts = [(x + (x - cxw) * 0.07, y + (y - cyw) * 0.22, sole_top + 0.012)
              for (x, y) in seq]
stitch = closed_curve("Boot_Stitch", stitch_pts, 0.0014, 3)

# ── Materiali clay (valuta forma) ────────────────────────────────────────────
def clay_mat(name, col, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m
m_leather = clay_mat("ClayLeather", (0.085, 0.075, 0.070), 0.55)
m_sole    = clay_mat("ClaySole",    (0.030, 0.030, 0.035), 0.80)
upper.data.materials.append(m_leather)
tongue.data.materials.append(m_leather)
sole.data.materials.append(m_sole)

# ── Studio: piano, camera, luci 3-punti ──────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.14, 0.0, -0.014))
ground = bpy.context.active_object
ground.name = "Ground"
gm = clay_mat("Ground", (0.05, 0.05, 0.055), 0.5)
ground.data.materials.append(gm)

target = Vector((0.13, 0.0, 0.13))
bpy.ops.object.camera_add(location=(0.95, -0.92, 0.40))
cam = bpy.context.active_object
d = target - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 70
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = d.length
cam.data.dof.aperture_fstop = 6.0
bpy.context.scene.camera = cam

def add_area(name, loc, energy, size, color):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.name = name
    L.data.energy = energy
    L.data.size = size
    L.data.color = color
    dd = target - L.location
    L.rotation_euler = dd.to_track_quat('-Z', 'Y').to_euler()
    return L

add_area("Key",  (0.75, -0.65, 0.95), 40, 0.55, (1.00, 0.97, 0.90))
add_area("Fill", (-0.55, -0.45, 0.50),  8, 1.10, (0.87, 0.93, 1.00))
add_area("Rim",  (-0.20,  0.70, 0.75), 26, 0.35, (1.00, 0.96, 0.92))

world = bpy.context.scene.world
world.use_nodes = True
wbg = world.node_tree.nodes.get("Background")
wbg.inputs["Color"].default_value = (0.02, 0.02, 0.025, 1.0)
wbg.inputs["Strength"].default_value = 0.12

result = {
    "objects": [o.name for o in bpy.data.objects],
    "upper": [len(upper.data.vertices), len(upper.data.polygons)],
    "sole":  [len(sole.data.vertices), len(sole.data.polygons)],
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# V3 — COLLARE + OCCHIELLI + LACCI  (additivo, non pulisce la scena)
# ─────────────────────────────────────────────────────────────────────────────
V3_ADD = r"""
import bpy, math
from mathutils import Vector, Quaternion

upper = bpy.data.objects["Boot_Upper"]

# LINEA-LACCI condivisa: identica a THROAT_P0/P1 di V2 (instep -> collare)
LP0 = Vector((0.150, 0.0, 0.082))
LP1 = Vector((0.052, 0.0, 0.292))
def throat_pt(s):
    return LP0 + (LP1 - LP0) * s

NEY = 8
s_vals = [0.05 + i * (0.90 / (NEY - 1)) for i in range(NEY)]
Y_OFF = 0.024

def surf_normal(s, side):
    # normale approx della superficie throat (esce di lato e in alto)
    n = Vector((0.30, side * 0.92, 0.22))
    n.normalize()
    return n

mat_metal = bpy.data.materials.new("ClayMetal")
mat_metal.use_nodes = True
bm_ = mat_metal.node_tree.nodes.get("Principled BSDF")
bm_.inputs["Base Color"].default_value = (0.32, 0.30, 0.27, 1.0)
bm_.inputs["Metallic"].default_value = 1.0
bm_.inputs["Roughness"].default_value = 0.38

left, right = [], []
for idx, s in enumerate(s_vals):
    base = throat_pt(s)
    for side in (-1, 1):
        c = Vector((base.x, side * Y_OFF, base.z))
        n = surf_normal(s, side)
        c = c - n * 0.0015  # incassa leggermente l'occhiello nella pelle
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.0060, minor_radius=0.0018,
            major_segments=20, minor_segments=8,
            location=c)
        ey = bpy.context.active_object
        ey.name = f"Eyelet_{idx}_{'L' if side<0 else 'R'}"
        ey.rotation_mode = 'QUATERNION'
        ey.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(n)
        ey.data.materials.append(mat_metal)
        for p in ey.data.polygons:
            p.use_smooth = True
        # punto per il laccio: appena sopra l'occhiello
        lp = c + n * 0.0035
        (left if side < 0 else right).append(lp)

# ── LACCI: criss-cross tra le due file di occhielli ──────────────────────────
cu = bpy.data.curves.new("Laces", 'CURVE')
cu.dimensions = '3D'
cu.bevel_depth = 0.0058
cu.bevel_resolution = 4
cu.use_fill_caps = True

def add_spline(pts):
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p.x, p.y, p.z, 1.0)

# diagonale A: R0->L1->R2->L3->R4->L5->R6
A = []
for i in range(NEY):
    A.append(right[i] if i % 2 == 0 else left[i])
add_spline(A)
# diagonale B: L0->R1->L2->R3->L4->R5->L6
B = []
for i in range(NEY):
    B.append(left[i] if i % 2 == 0 else right[i])
add_spline(B)
# code: due tratti che pendono dall'alto
top_s = throat_pt(1.0)
for side, src in ((-1, left[-1]), (1, right[-1])):
    end = Vector((top_s.x + 0.02, side * 0.030, top_s.z - 0.06))
    add_spline([src, Vector((src.x + 0.01, side * 0.030, src.z + 0.01)), end])

lobj = bpy.data.objects.new("Boot_Laces", cu)
bpy.context.collection.objects.link(lobj)
mat_lace = bpy.data.materials.new("ClayLace")
mat_lace.use_nodes = True
bl_ = mat_lace.node_tree.nodes.get("Principled BSDF")
bl_.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1.0)
bl_.inputs["Roughness"].default_value = 0.72
lobj.data.materials.append(mat_lace)

# ── COLLARE imbottito attorno alla bocca dello stivale ───────────────────────
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.050, minor_radius=0.012,
    major_segments=44, minor_segments=14,
    location=(0.052, 0.0, 0.298))
collar = bpy.context.active_object
collar.name = "Boot_Collar"
collar.scale = (1.06, 1.0, 0.72)
m_leather = bpy.data.materials.get("ClayLeather")
collar.data.materials.append(m_leather)
for p in collar.data.polygons:
    p.use_smooth = True

# ── CUCITURE di costruzione (toe-cap + backstay) ─────────────────────────────
def stitch_curve(name, pts, bevel=0.0013):
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.bevel_depth = bevel
    c.bevel_resolution = 2
    c.use_fill_caps = True
    sp = c.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    ob = bpy.data.objects.new(name, c)
    bpy.context.collection.objects.link(ob)
    return ob

# toe-cap: arco trasversale sul collo del piede (~x 0.205)
toe_pts = []
for k in range(25):
    u = -1.0 + 2.0 * k / 24
    y = u * 0.050
    x = 0.205 + (1.0 - u * u) * 0.012
    z = 0.060 - (u * u) * 0.034 + 0.003
    toe_pts.append((x, y, z))
stitch_curve("Boot_ToeStitch", toe_pts)

# backstay: cucitura verticale dietro al tallone/gambale
back_pts = []
for k in range(20):
    s = k / 19.0
    z = 0.040 + s * 0.245
    x = -0.004 + (0.006 if z > 0.10 else 0.0)
    back_pts.append((x, 0.0, z))
stitch_curve("Boot_BackStitch", back_pts, bevel=0.0015)

result = {"objects": len(bpy.data.objects),
          "eyelets": NEY * 2,
          "lace_splines": len(cu.splines)}
"""

# ─────────────────────────────────────────────────────────────────────────────
# V4 — MATERIALI PBR PROCEDURALI (pelle, gomma+lug, metallo, cordino, cuciture)
# ─────────────────────────────────────────────────────────────────────────────
V4_MAT = r"""
import bpy

def new_mat(name):
    if name in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[name])
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf

def set_in(bsdf, key, val):
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = val

def tex_coord(nt, mode="Object"):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs[mode], mp.inputs["Vector"])
    return mp

# ── PELLE full-grain ─────────────────────────────────────────────────────────
def leather_mat(name, base):
    m, nt, b = new_mat(name)
    set_in(b, "Metallic", 0.0)
    set_in(b, "Specular IOR Level", 0.42)
    set_in(b, "Coat Weight", 0.0)
    set_in(b, "Sheen Weight", 0.04)
    mp = tex_coord(nt)
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    # screziatura colore (low-freq) -> Base Color
    cv = nt.nodes.new("ShaderNodeTexNoise")
    cv.inputs["Scale"].default_value = 7.0
    cv.inputs["Detail"].default_value = 2.0
    nt.links.new(mp.outputs["Vector"], cv.inputs["Vector"])
    cramp = nt.nodes.new("ShaderNodeValToRGB")
    dark = tuple(c * 0.55 for c in base)
    lite = tuple(min(c * 1.15, 1.0) for c in base)
    cramp.color_ramp.elements[0].color = (*dark, 1.0)
    cramp.color_ramp.elements[1].color = (*lite, 1.0)
    cramp.color_ramp.elements[0].position = 0.22
    cramp.color_ramp.elements[1].position = 0.86
    nt.links.new(cv.outputs["Fac"], cramp.inputs["Fac"])
    nt.links.new(cramp.outputs["Color"], b.inputs["Base Color"])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 320.0
    grain.inputs["Detail"].default_value = 5.0
    nt.links.new(mp.outputs["Vector"], grain.inputs["Vector"])
    pores = nt.nodes.new("ShaderNodeTexVoronoi")
    pores.inputs["Scale"].default_value = 220.0
    nt.links.new(mp.outputs["Vector"], pores.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.inputs["Factor"].default_value = 0.45
    nt.links.new(grain.outputs["Fac"], mix.inputs[6])
    nt.links.new(pores.outputs["Distance"], mix.inputs[7])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.17
    bump.inputs["Distance"].default_value = 0.0035
    nt.links.new(mix.outputs[2], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    rn = nt.nodes.new("ShaderNodeTexNoise")
    rn.inputs["Scale"].default_value = 14.0
    nt.links.new(mp.outputs["Vector"], rn.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = 0.46
    mr.inputs["To Max"].default_value = 0.66
    nt.links.new(rn.outputs["Fac"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    return m

# ── GOMMA suola con lug tread (bump procedurale) ─────────────────────────────
def rubber_mat(name, base):
    m, nt, b = new_mat(name)
    set_in(b, "Base Color", (*base, 1.0))
    set_in(b, "Metallic", 0.0)
    set_in(b, "Specular IOR Level", 0.30)
    set_in(b, "Roughness", 0.78)
    mp = tex_coord(nt)
    lug = nt.nodes.new("ShaderNodeTexVoronoi")
    lug.feature = 'F1'
    lug.inputs["Scale"].default_value = 48.0
    nt.links.new(mp.outputs["Vector"], lug.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = 'CONSTANT'
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[1].position = 0.55
    nt.links.new(lug.outputs["Distance"], ramp.inputs["Fac"])
    micro = nt.nodes.new("ShaderNodeTexNoise")
    micro.inputs["Scale"].default_value = 300.0
    nt.links.new(mp.outputs["Vector"], micro.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.inputs["Factor"].default_value = 0.25
    nt.links.new(ramp.outputs["Color"], mix.inputs[6])
    nt.links.new(micro.outputs["Fac"], mix.inputs[7])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.85
    bump.inputs["Distance"].default_value = 0.010
    nt.links.new(mix.outputs[2], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m

def metal_mat(name, base, rough):
    m, nt, b = new_mat(name)
    set_in(b, "Base Color", (*base, 1.0))
    set_in(b, "Metallic", 1.0)
    set_in(b, "Roughness", rough)
    mp = tex_coord(nt)
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 400.0
    nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m

def cord_mat(name, base):
    m, nt, b = new_mat(name)
    set_in(b, "Base Color", (*base, 1.0))
    set_in(b, "Roughness", 0.72)
    set_in(b, "Sheen Weight", 0.25)
    mp = tex_coord(nt)
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = 'RINGS'
    wv.inputs["Scale"].default_value = 130.0
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.30
    nt.links.new(wv.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m

def simple_mat(name, base, rough, metal=0.0):
    m, nt, b = new_mat(name)
    set_in(b, "Base Color", (*base, 1.0))
    set_in(b, "Roughness", rough)
    set_in(b, "Metallic", metal)
    return m

LEATHER = (0.055, 0.029, 0.013)   # marrone scuro militare (lineare)
m_leather = leather_mat("Leather", LEATHER)
m_weltlea = leather_mat("WeltLeather", (0.030, 0.020, 0.014))
m_rubber  = rubber_mat("SoleRubber", (0.012, 0.012, 0.014))
m_metal   = metal_mat("EyeletMetal", (0.050, 0.048, 0.052), 0.34)
m_cord    = cord_mat("LaceCord", (0.034, 0.026, 0.018))
m_stitch  = simple_mat("Stitch", (0.34, 0.16, 0.020), 0.55)
m_ground  = simple_mat("GroundStudio", (0.018, 0.018, 0.020), 0.34)

def assign(obj_name, mat):
    o = bpy.data.objects.get(obj_name)
    if not o:
        return
    o.data.materials.clear()
    o.data.materials.append(mat)

for nm in ("Boot_Upper", "Boot_Tongue", "Boot_Collar"):
    assign(nm, m_leather)
assign("Boot_Sole", m_rubber)
assign("Boot_Welt", m_weltlea)
assign("Boot_Laces", m_cord)
assign("Ground", m_ground)
for o in bpy.data.objects:
    if o.name.endswith("Stitch"):
        o.data.materials.clear()
        o.data.materials.append(m_stitch)
    elif o.name.startswith("Eyelet_"):
        o.data.materials.clear()
        o.data.materials.append(m_metal)

result = {"mats": [m.name for m in bpy.data.materials],
          "ground_ok": bpy.data.objects.get("Ground") is not None}
"""

# ─────────────────────────────────────────────────────────────────────────────
# V5 — STUDIO PRODOTTO (sweep + key/fill/rim dark-product + camera hero)
# ─────────────────────────────────────────────────────────────────────────────
V5_SCENE = r"""
import bpy, bmesh, math
from mathutils import Vector

# rimuovi vecchio studio clay (luci/camera/ground)
for nm in ("Camera", "Key", "Fill", "Rim", "Ground"):
    o = bpy.data.objects.get(nm)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)

# ── SWEEP / ciclorama: pavimento che curva su a parete ───────────────────────
me = bpy.data.meshes.new("Sweep")
sweep = bpy.data.objects.new("Sweep", me)
bpy.context.collection.objects.link(sweep)
bm = bmesh.new()
# profilo nel piano Y-Z: piano davanti -> curva -> parete dietro
prof = []
y = -1.2
while y < 0.20:
    prof.append((y, -0.014)); y += 0.15
for k in range(1, 13):       # raccordo curvo
    a = (math.pi / 2) * k / 12
    prof.append((0.20 + 0.55 * math.sin(a), -0.014 + 0.55 * (1 - math.cos(a))))
prof.append((0.75, 1.4))
rows = []
for (yy, zz) in prof:
    rows.append([bm.verts.new((xx, yy, zz)) for xx in (-1.6, 1.8)])
for a, b in zip(rows[:-1], rows[1:]):
    bm.faces.new([a[0], a[1], b[1], b[0]])
bm.normal_update()
bm.to_mesh(me); bm.free(); me.update()
for p in sweep.data.polygons:
    p.use_smooth = True
mg = bpy.data.materials.get("GroundStudio")
if mg:
    b = mg.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Roughness"].default_value = 0.30
    sweep.data.materials.append(mg)

# ── Camera hero 3/4 ──────────────────────────────────────────────────────────
target = Vector((0.135, 0.0, 0.125))
bpy.ops.object.camera_add(location=(0.92, -0.86, 0.34))
cam = bpy.context.active_object
cam.name = "Camera"
d = target - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 80
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = (Vector((0.20, 0.0, 0.09)) - cam.location).length
cam.data.dof.aperture_fstop = 4.0
bpy.context.scene.camera = cam

def add_area(name, loc, energy, size, color, tgt=target):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.name = name
    L.data.energy = energy
    L.data.size = size
    L.data.color = color
    dd = tgt - L.location
    L.rotation_euler = dd.to_track_quat('-Z', 'Y').to_euler()
    return L

# dark-product: key calda, fill fredda debole, RIM forte (stacca pelle scura)
add_area("Key",    (0.55, -0.95, 1.15), 105, 0.70, (1.00, 0.95, 0.86))
add_area("Fill",   (1.15, -0.55, 0.55),  16, 1.50, (0.84, 0.91, 1.00))
add_area("Rim",    (-0.05, 0.95, 1.00), 165, 0.26, (1.00, 0.94, 0.84))
add_area("Kick",   (-0.70, -0.20, 0.45),  34, 0.55, (1.00, 0.96, 0.90))

world = bpy.context.scene.world
world.use_nodes = True
wbg = world.node_tree.nodes.get("Background")
wbg.inputs["Color"].default_value = (0.012, 0.012, 0.015, 1.0)
wbg.inputs["Strength"].default_value = 0.05

sc = bpy.context.scene
try:
    sc.eevee.use_raytracing = True
    sc.eevee.ray_tracing_options.use_denoise = True
except Exception:
    pass

result = {"lights": [o.name for o in bpy.data.objects if o.type == 'LIGHT'],
          "cam": bpy.context.scene.camera.name}
"""

if __name__ == "__main__":
    print("=" * 55)
    print("COMBAT BOOT — v5 (studio prodotto + render finale)")
    print("=" * 55)
    r = blender(V2_BUILD, timeout=120)
    print("  v2 build ->", r)
    if r:
        r3 = blender(V3_ADD, timeout=90)
        print("  v3 add   ->", r3)
        r4 = blender(V4_MAT, timeout=90)
        print("  v4 mat   ->", r4)
        r5 = blender(V5_SCENE, timeout=90)
        print("  v5 scene ->", r5)
        if r3 and r4 and r5:
            render_save(f"{RENDER_DIR}/boot_v5.png",
                        w=1600, h=1200, samples=200, exposure=-0.30)
    print("Done.")
