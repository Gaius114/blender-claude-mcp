import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# combat_boot_v2.py — Stivale combat, pipeline coordinatore
# Fix: esposizione corretta, assegnazione materiale robusta
# ============================================================


# ── PARALLEL TRANSPORT ──────────────────────────────────────

def _pt_step(prev_d, prev_N, prev_B, new_d):
    new_d = new_d.normalized()
    rot   = prev_d.rotation_difference(new_d)
    return new_d, (rot @ prev_N).normalized(), (rot @ prev_B).normalized()


# ── SUPERELLISSE ────────────────────────────────────────────

def _superellipse_ring(bm, center, N, B, rx, ry, n, seg):
    verts = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        c, s = math.cos(a), math.sin(a)
        x = math.copysign(abs(c) ** (2.0 / n), c) * rx
        y = math.copysign(abs(s) ** (2.0 / n), s) * ry
        verts.append(bm.verts.new(center + N * x + B * y))
    return verts


def _bridge(bm, ra, rb):
    seg = len(ra)
    for k in range(seg):
        bm.faces.new([ra[k], ra[(k+1)%seg], rb[(k+1)%seg], rb[k]])


def _fan_cap(bm, ring_verts, flip=False):
    cx = sum((v.co for v in ring_verts), Vector()) / len(ring_verts)
    cv = bm.verts.new(cx)
    seg = len(ring_verts)
    for k in range(seg):
        nk = (k + 1) % seg
        if flip:
            bm.faces.new([cv, ring_verts[nk], ring_verts[k]])
        else:
            bm.faces.new([cv, ring_verts[k], ring_verts[nk]])


# ── BUILD UPPER ─────────────────────────────────────────────

def _build_upper(H, side, seg):
    FL   = 0.152 * H
    FH   = 0.038 * H
    COLL = 0.072 * H
    SL   = 0.014 * H
    SOLE_Z = -(FH + SL)

    spine = [
        Vector((0,  0.000,  COLL)),
        Vector((0,  0.000,  0.000)),
        Vector((0, -0.015*H, SOLE_Z*0.60)),
        Vector((0,  0.020*H, SOLE_Z*0.85)),
        Vector((0,  0.065*H, SOLE_Z)),
        Vector((0,  0.105*H, SOLE_Z)),
        Vector((0,  0.138*H, SOLE_Z)),
        Vector((0,  0.152*H, SOLE_Z)),
    ]

    prof = [
        (0.048*H, 0.044*H, 0.040*H, 2.2),
        (0.040*H, 0.037*H, 0.034*H, 2.5),
        (0.036*H, 0.033*H, 0.030*H, 2.8),
        (0.038*H, 0.034*H, 0.026*H, 3.0),
        (0.042*H, 0.038*H, 0.024*H, 3.2),
        (0.046*H, 0.042*H, 0.024*H, 3.4),
        (0.044*H, 0.040*H, 0.022*H, 3.5),
        (0.036*H, 0.033*H, 0.020*H, 3.5),
    ]

    bm = bmesh.new()
    N = Vector((side, 0, 0))
    B = Vector((0, 0, 1))
    d = (spine[1] - spine[0]).normalized()

    rings = []
    for i, (pt, (rx_m, rx_l, ry, n)) in enumerate(zip(spine, prof)):
        if i > 0:
            nd = (spine[i] - spine[i-1]).normalized()
            d, N, B = _pt_step(d, N, B, nd)
        verts = []
        for k in range(seg):
            a   = 2 * math.pi * k / seg
            c   = math.cos(a)
            s   = math.sin(a)
            rx  = rx_m if c >= 0 else rx_l
            x   = math.copysign(abs(c) ** (2.0 / n), c) * rx
            y   = math.copysign(abs(s) ** (2.0 / n), s) * ry
            verts.append(bm.verts.new(pt + N * x + B * y))
        rings.append(verts)

    for i in range(len(rings) - 1):
        _bridge(bm, rings[i], rings[i+1])

    _fan_cap(bm, rings[0], flip=True)
    _fan_cap(bm, rings[-1], flip=False)

    return bm, rings[-2]


# ── BUILD SOLE ──────────────────────────────────────────────

def _build_sole(H, side, seg_sole=32):
    FH   = 0.038 * H
    SL   = 0.014 * H
    SOLE_Z = -(FH + SL)
    WELT = 0.004 * H
    top_z = SOLE_Z
    bot_z = SOLE_Z - SL

    def bootprint(n_pts=seg_sole):
        pts = []
        for k in range(n_pts):
            a = 2 * math.pi * k / n_pts
            c, s = math.cos(a), math.sin(a)
            rx = (0.052*H + WELT) * (1.0 + 0.08 * side * c)
            ry_f = 0.088 * H + WELT
            ry_b = 0.068 * H + WELT
            ry   = ry_f if s >= 0 else ry_b
            x = math.copysign(abs(c) ** (2.0/3.0), c) * rx
            y = math.copysign(abs(s) ** (2.0/2.5), s) * ry
            pts.append(Vector((x, y + 0.018*H, top_z)))
        return pts

    bm = bmesh.new()
    top_pts = bootprint()
    top_verts = [bm.verts.new(p) for p in top_pts]
    bot_verts = [bm.verts.new(Vector((p.x, p.y, bot_z))) for p in top_pts]

    n = len(top_verts)
    for k in range(n):
        bm.faces.new([top_verts[k], top_verts[(k+1)%n],
                      bot_verts[(k+1)%n], bot_verts[k]])
    bm.faces.new(top_verts[::-1])
    bm.faces.new(bot_verts)

    return bm


# ── BUILD HEEL BLOCK ────────────────────────────────────────

def _build_heel(H):
    FH   = 0.038 * H
    SL   = 0.014 * H
    HL   = 0.030 * H
    HRX  = 0.034 * H
    HRY  = 0.025 * H
    BEVEL= 0.005 * H
    CY   = -0.022 * H
    top_z = -(FH + SL)
    bot_z = top_z - HL

    bm = bmesh.new()

    def heel_ring(z, shrink=0.0):
        rx = HRX - shrink
        ry = HRY - shrink
        n  = 4.0
        seg = 24
        return [bm.verts.new(Vector((
            math.copysign(abs(math.cos(2*math.pi*k/seg))**(2/n), math.cos(2*math.pi*k/seg)) * rx,
            CY + math.copysign(abs(math.sin(2*math.pi*k/seg))**(2/n), math.sin(2*math.pi*k/seg)) * ry,
            z
        ))) for k in range(seg)]

    top_ring = heel_ring(top_z, shrink=BEVEL*0.5)
    bot_ring = heel_ring(bot_z, shrink=0)

    _bridge(bm, top_ring, bot_ring)
    _fan_cap(bm, top_ring, flip=True)
    _fan_cap(bm, bot_ring, flip=False)

    return bm


# ── BUILD COMBAT BOOT ───────────────────────────────────────

def build_combat_boot(H=1.80, side=1, seg=20, name=None):
    if name is None:
        name = "Boot_L" if side > 0 else "Boot_R"

    bm_upper, _ = _build_upper(H, side, seg)
    bm_sole     = _build_sole(H, side)
    bm_heel     = _build_heel(H)

    bm_final = bmesh.new()
    for bm_src in (bm_upper, bm_sole, bm_heel):
        tmp_me = bpy.data.meshes.new("_boot_tmp")
        bm_src.to_mesh(tmp_me)
        bm_final.from_mesh(tmp_me)
        bpy.data.meshes.remove(tmp_me)
        bm_src.free()

    bmesh.ops.remove_doubles(bm_final, verts=bm_final.verts, dist=0.0008)
    bm_final.normal_update()

    me = bpy.data.meshes.new(name + "_m")
    bm_final.to_mesh(me)
    bm_final.free()

    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    sm = ob.modifiers.new("Sub", "SUBSURF")
    sm.levels = 2
    sm.render_levels = 3
    ob.data.shade_smooth()

    return ob, {"ankle": Vector((0, 0, 0))}


# ============================================================
# PIPELINE COORDINATORE — 3 fasi separate
# ============================================================

# ── PULIZIA SCENA ───────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials,
            bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
    for d in list(blk):
        try: blk.remove(d)
        except: pass

H = 1.80

# ── FASE 1 — BUILD ──────────────────────────────────────────
boot, sockets = build_combat_boot(H=H, side=+1, seg=20, name="Boot_L")

# ── FASE 2 — ASSEMBLY (posizionamento) ──────────────────────
# Il boot è già all'origine con la caviglia a (0,0,0): nessun riposizionamento.

FH   = 0.038 * H
SL   = 0.014 * H
GND  = -(FH + SL + SL)          # piano suolo sotto la suola
FCY  = 0.040 * H                 # centro Y del bounding box stivale
FCZ  = -(FH + SL) * 0.4         # centro Z del bounding box stivale

bpy.ops.mesh.primitive_plane_add(size=1.2, location=(0, FCY, GND))
floor_ob = bpy.context.active_object
floor_ob.name = "Floor"

# ── FASE 3 — MATERIAL ───────────────────────────────────────

# CUOIO NERO — pattern robusto: svuota slot, aggiungi, imposta active
mp = bpy.data.materials.new("Leather_Black")
mp.use_nodes = True
nt = mp.node_tree
bp = nt.nodes.get("Principled BSDF")
if bp is None:
    bp = nt.nodes.new('ShaderNodeBsdfPrincipled')
    out = nt.nodes.get("Material Output") or nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(bp.outputs['BSDF'], out.inputs['Surface'])

bp.inputs['Base Color'].default_value = (0.025, 0.022, 0.018, 1)
bp.inputs['Roughness'].default_value  = 0.72
inp_names = [i.name for i in bp.inputs]
if 'Specular IOR Level' in inp_names:
    bp.inputs['Specular IOR Level'].default_value = 0.28
elif 'Specular' in inp_names:
    bp.inputs['Specular'].default_value = 0.28

# grana cuoio (bump)
noi = nt.nodes.new('ShaderNodeTexNoise')
noi.location = (-400, -200)
noi.inputs['Scale'].default_value     = 220.0
noi.inputs['Detail'].default_value    = 8.0
noi.inputs['Roughness'].default_value = 0.65
bmp = nt.nodes.new('ShaderNodeBump')
bmp.location = (-160, -200)
bmp.inputs['Strength'].default_value  = 0.18
bmp.inputs['Distance'].default_value  = 0.002
nt.links.new(noi.outputs['Fac'],    bmp.inputs['Height'])
nt.links.new(bmp.outputs['Normal'], bp.inputs['Normal'])

# assegnazione robusta: svuota → aggiungi → imposta active
while len(boot.data.materials) > 0:
    boot.data.materials.pop(index=0, update_data=True)
boot.data.materials.append(mp)
bpy.context.view_layer.objects.active = boot
boot.active_material_index = 0

print(f"[mat] boot slots={len(boot.data.materials)}  mat0={boot.data.materials[0].name}")

# PAVIMENTO — grigio scuro neutro
mf = bpy.data.materials.new("Floor_Mat")
mf.use_nodes = True
pf = mf.node_tree.nodes.get("Principled BSDF")
pf.inputs['Base Color'].default_value = (0.08, 0.08, 0.09, 1)
pf.inputs['Roughness'].default_value  = 0.90
while len(floor_ob.data.materials) > 0:
    floor_ob.data.materials.pop(index=0, update_data=True)
floor_ob.data.materials.append(mf)

# ── LUCI — preset dark_product scalato per oggetto ~0.27m ───
# Riferimento 1m → scala energia per (0.27)^2 ≈ factor 0.073
# key=400W*0.073≈29W, fill=50W*0.073≈4W, rim=250W*0.073≈18W
TGT = Vector((0, FCY, FCZ))

def area(nm, e, sz, loc, col=(1,1,1)):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object
    L.name = nm
    L.data.energy = e
    L.data.size   = sz
    L.data.color  = col
    d = TGT - Vector(loc)
    L.rotation_euler = d.to_track_quat('-Z','Y').to_euler()

area("Key",  28, 0.30, (-0.26, -0.26, 0.30), (1.00, 0.96, 0.90))
area("Fill",  4, 0.55, ( 0.24, -0.16, 0.14), (0.88, 0.94, 1.00))
area("Rim",  18, 0.14, ( 0.02,  0.32, 0.24), (1.00, 0.98, 0.93))
area("Bot",   2, 0.45, ( 0.00,  FCY,  GND + 0.06), (0.80, 0.80, 0.78))

world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.006, 0.007, 0.010, 1)
bg.inputs[1].default_value = 0.03

# ── CAMERA 3/4 ──────────────────────────────────────────────
bpy.ops.object.empty_add(type='PLAIN_AXES', location=TGT)
tg = bpy.context.active_object
tg.name = "Target"

bpy.ops.object.camera_add(location=(-0.30, -0.56, 0.22))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 85
tt = cam.constraints.new('TRACK_TO')
tt.target = tg
tt.track_axis  = 'TRACK_NEGATIVE_Z'
tt.up_axis     = 'UP_Y'
bpy.context.scene.camera = cam

# ── RENDER ──────────────────────────────────────────────────
sc = bpy.context.scene
try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
ev = sc.eevee
if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 128
if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True

sc.render.resolution_x = 1000
sc.render.resolution_y = 800
sc.render.image_settings.file_format = 'PNG'
sc.render.use_compositing = False

try:
    sc.view_settings.view_transform = "AgX"
    for lk in ("AgX - Medium Low Contrast", "AgX - Base Contrast", "None"):
        try: sc.view_settings.look = lk; break
        except: pass
except:
    pass

sc.view_settings.exposure = 0.0    # neutro — no sovraesposizione

sc.render.filepath = "D:/blender-claude/renders/combat_boot_v2.png"
bpy.ops.render.render(write_still=True)
print(f"[boot] verts={len(boot.data.vertices)}  saved→{sc.render.filepath}")
