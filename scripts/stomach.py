import bpy, bmesh, math
from mathutils import Vector, Quaternion

# ============================================================
# STOMACO UMANO ANATOMICO COMPLETO
# esofago -> cardias -> fundus -> corpo -> antro -> piloro -> duodeno (C)
# Tecnica: build_shell su spine curva, sezione ellittica appiattita in Y
# ============================================================

# ---- CLEAR SCENE ----
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.curves):
    for d in list(blk):
        blk.remove(d)

# ---- SPINE + RAGGIO (control points) ----
CTRL = [
    ((-0.05, 0.0, 3.50), 0.135),  # esofago top
    ((-0.11, 0.0, 3.08), 0.135),  # esofago mid
    ((-0.17, 0.0, 2.78), 0.155),  # esofago basso
    ((-0.24, 0.0, 2.55), 0.26),   # cardias
    ((-0.50, 0.0, 2.60), 0.44),   # incisura / notch in
    ((-0.88, 0.0, 2.62), 0.62),   # fundus apex
    ((-1.04, 0.0, 2.22), 0.70),   # fundus down
    ((-0.97, 0.0, 1.78), 0.78),   # corpo alto
    ((-0.80, 0.0, 1.28), 0.74),   # corpo medio
    ((-0.50, 0.0, 0.85), 0.62),   # corpo basso
    ((-0.05, 0.0, 0.55), 0.45),   # antro 1
    (( 0.45, 0.0, 0.45), 0.34),   # antro 2
    (( 0.80, 0.0, 0.50), 0.17),   # piloro
    (( 0.95, 0.0, 0.56), 0.15),   # piloro canale
    (( 1.15, 0.0, 0.62), 0.21),   # duodeno 1
    (( 1.35, 0.0, 0.40), 0.20),   # duodeno 2
    (( 1.35, 0.0, 0.00), 0.20),   # duodeno 3
    (( 1.05, 0.0,-0.20), 0.19),   # duodeno 4
    (( 0.75, 0.0,-0.18), 0.18),   # duodeno 5
]
PTS  = [Vector(p) for p, r in CTRL]
RAD  = [r for p, r in CTRL]
Y_FLAT = 0.62          # appiattimento antero-posteriore
SEG    = 48            # segmenti per anello
SUBDIV = 7             # campioni Catmull-Rom tra control point

# ---- CATMULL-ROM ----
def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) +
                  (-p0 + p2) * t +
                  (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                  (-p0 + 3 * p1 - 3 * p2 + p3) * t3)

def catmull_scalar(a0, a1, a2, a3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * a1) +
                  (-a0 + a2) * t +
                  (2 * a0 - 5 * a1 + 4 * a2 - a3) * t2 +
                  (-a0 + 3 * a1 - 3 * a2 + a3) * t3)

def resample(points, radii, sub):
    n = len(points)
    sp, sr = [], []
    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(i + 2, n - 1)]
        r0 = radii[max(i - 1, 0)]
        r1 = radii[i]
        r2 = radii[i + 1]
        r3 = radii[min(i + 2, n - 1)]
        steps = sub if i < n - 2 else sub + 1
        for s in range(steps):
            t = s / sub
            sp.append(catmull(p0, p1, p2, p3, t))
            sr.append(max(0.02, catmull_scalar(r0, r1, r2, r3, t)))
    return sp, sr

SPINE, RADII = resample(PTS, RAD, SUBDIV)

# ---- PARALLEL TRANSPORT ----
def parallel_transport(points):
    n = len(points)
    frames = [None] * n
    T0 = (points[1] - points[0]).normalized()
    up = Vector((0, 1, 0))
    if abs(T0.dot(up)) > 0.99:
        up = Vector((1, 0, 0))
    N0 = T0.cross(up).normalized()
    B0 = T0.cross(N0).normalized()
    frames[0] = (T0, N0, B0)
    for i in range(1, n):
        T_prev, N_prev, B_prev = frames[i - 1]
        if i < n - 1:
            T_curr = (points[i + 1] - points[i - 1]).normalized()
        else:
            T_curr = (points[i] - points[i - 1]).normalized()
        axis = T_prev.cross(T_curr)
        if axis.length > 1e-8:
            axis.normalize()
            cos_a = max(-1.0, min(1.0, T_prev.dot(T_curr)))
            ang = math.acos(cos_a)
            q = Quaternion(axis, ang)
            N_curr = (q @ N_prev)
        else:
            N_curr = N_prev.copy()
        # reortho ogni 12 step (e sempre, leggero)
        N_curr = (N_curr - T_curr * T_curr.dot(N_curr)).normalized()
        B_curr = T_curr.cross(N_curr).normalized()
        N_curr = B_curr.cross(T_curr).normalized()
        frames[i] = (T_curr, N_curr, B_curr)
    return frames

FRAMES = parallel_transport(SPINE)

# ---- BUILD SHELL ----
bm = bmesh.new()
rings = []
for pt, (T, N, B), r in zip(SPINE, FRAMES, RADII):
    ring = []
    for j in range(SEG):
        a = 2 * math.pi * j / SEG
        # ellisse appiattita: N = asse "largo", B = asse profondita' (Y_FLAT)
        off = N * (r * math.cos(a)) + B * (r * Y_FLAT * math.sin(a))
        ring.append(bm.verts.new(pt + off))
    rings.append(ring)

bm.verts.ensure_lookup_table()

for ri in range(len(rings) - 1):
    r0, r1 = rings[ri], rings[ri + 1]
    for j in range(SEG):
        nj = (j + 1) % SEG
        bm.faces.new([r0[j], r0[nj], r1[nj], r1[j]])

# cap esofago (inizio) - taglio quasi piatto (lume del tubo)
c_start = bm.verts.new(SPINE[0] - FRAMES[0][0] * RADII[0] * 0.05)
for j in range(SEG):
    nj = (j + 1) % SEG
    bm.faces.new([rings[0][nj], rings[0][j], c_start])

# cap duodeno (fine) - fan
c_end = bm.verts.new(SPINE[-1] + FRAMES[-1][0] * RADII[-1] * 0.3)
for j in range(SEG):
    nj = (j + 1) % SEG
    bm.faces.new([rings[-1][j], rings[-1][nj], c_end])

bm.normal_update()
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
mesh = bpy.data.meshes.new("Stomaco_mesh")
bm.to_mesh(mesh)
bm.free()
obj = bpy.data.objects.new("Stomaco", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

# normali coerenti verso l'esterno
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')

# SubSurf + smooth
sub = obj.modifiers.new("Subsurf", "SUBSURF")
sub.levels = 2
sub.render_levels = 3
obj.data.shade_smooth()

# origin al centro geometrico
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

# ---- MATERIALE: Sierosa_Gastrica ----
m = bpy.data.materials.new("Sierosa_Gastrica")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
out  = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (700, 0)
bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled');  bsdf.location = (320, 0)
inp = [i.name for i in bsdf.inputs]

bsdf.inputs['Base Color'].default_value = (0.62, 0.30, 0.27, 1.0)
for s in ('Subsurface Weight', 'Subsurface'):
    if s in inp: bsdf.inputs[s].default_value = 0.28; break
if 'Subsurface Radius' in inp:
    bsdf.inputs['Subsurface Radius'].default_value = (0.42, 0.16, 0.12)
if 'Subsurface Scale' in inp:
    bsdf.inputs['Subsurface Scale'].default_value = 0.06
try: bsdf.subsurface_method = 'RANDOM_WALK'
except: pass
for s in ('Coat Weight', 'Clearcoat'):
    if s in inp: bsdf.inputs[s].default_value = 0.26; break
for s in ('Coat Roughness', 'Clearcoat Roughness'):
    if s in inp: bsdf.inputs[s].default_value = 0.20; break

# roughness procedurale (aspetto umido non uniforme)
rtex = nt.nodes.new('ShaderNodeTexNoise'); rtex.location = (-300, 220)
rtex.inputs['Scale'].default_value = 10.0
rtex.inputs['Detail'].default_value = 4.0
rramp = nt.nodes.new('ShaderNodeValToRGB'); rramp.location = (-40, 220)
rramp.color_ramp.elements[0].position = 0.30
rramp.color_ramp.elements[0].color = (0.28, 0.28, 0.28, 1.0)
rramp.color_ramp.elements[1].position = 0.75
rramp.color_ramp.elements[1].color = (0.45, 0.45, 0.45, 1.0)
nt.links.new(rtex.outputs['Fac'], rramp.inputs['Fac'])
nt.links.new(rramp.outputs['Color'], bsdf.inputs['Roughness'])

# bump micro-irregolarita'
btex = nt.nodes.new('ShaderNodeTexNoise'); btex.location = (-300, -260)
btex.inputs['Scale'].default_value = 45.0
btex.inputs['Detail'].default_value = 5.0
bump = nt.nodes.new('ShaderNodeBump'); bump.location = (-20, -260)
bump.inputs['Strength'].default_value = 0.10
bump.inputs['Distance'].default_value = 0.003
nt.links.new(btex.outputs['Fac'], bump.inputs['Height'])
nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

# mottatura vascolare sul base color
vtex = nt.nodes.new('ShaderNodeTexNoise'); vtex.location = (-460, 0)
vtex.inputs['Scale'].default_value = 5.5
vtex.inputs['Detail'].default_value = 4.0
vtex.inputs['Roughness'].default_value = 0.6
vcr = nt.nodes.new('ShaderNodeValToRGB'); vcr.location = (-260, 0)
vcr.color_ramp.elements[0].position = 0.32
vcr.color_ramp.elements[1].position = 0.68
vmix = nt.nodes.new('ShaderNodeMix'); vmix.location = (60, 0)
vmix.data_type = 'RGBA'
vmix.blend_type = 'MIX'
vmix.inputs[6].default_value = (0.64, 0.31, 0.28, 1.0)
vmix.inputs[7].default_value = (0.50, 0.155, 0.155, 1.0)
nt.links.new(vtex.outputs['Fac'], vcr.inputs['Fac'])
nt.links.new(vcr.outputs['Color'], vmix.inputs[0])
nt.links.new(vmix.outputs[2], bsdf.inputs['Base Color'])

nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

obj.data.materials.clear()
obj.data.materials.append(m)

# ---- FLOOR ----
import math as _m
mn_z = min(v.co.z + obj.location.z for v in obj.data.vertices)
bpy.ops.mesh.primitive_plane_add(size=40, location=(-0.1, 0.0, mn_z - 0.55))
floor = bpy.context.active_object
floor.name = "Floor"
fm = bpy.data.materials.new("Pavimento")
fm.use_nodes = True
fnt = fm.node_tree; fnt.nodes.clear()
fo = fnt.nodes.new('ShaderNodeOutputMaterial'); fo.location = (300, 0)
fb = fnt.nodes.new('ShaderNodeBsdfPrincipled'); fb.location = (0, 0)
fb.inputs['Base Color'].default_value = (0.055, 0.055, 0.065, 1.0)
fb.inputs['Roughness'].default_value = 0.88
fnt.links.new(fb.outputs['BSDF'], fo.inputs['Surface'])
floor.data.materials.append(fm)

# ---- CAMERA ----
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(-0.10, 0.0, 1.45))
tgt = bpy.context.active_object
tgt.name = "CamTarget"
bpy.ops.object.camera_add(location=(2.6, -12.5, 3.4))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 55
tt = cam.constraints.new('TRACK_TO')
tt.target = tgt
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

# ---- LIGHTS (soft, organic) ----
def area(name, energy, size, pos, color=(1.0, 0.96, 0.90)):
    bpy.ops.object.light_add(type='AREA', location=pos)
    L = bpy.context.active_object
    L.name = name
    L.data.energy = energy
    L.data.size = size
    L.data.color = color
    d = Vector((-0.1, 0.0, 1.45)) - Vector(pos)
    L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return L

area("Key_Light",  1500, 5.0, (-3.2, -5.0, 5.0), (1.0, 0.95, 0.88))
area("Fill_Light",  420, 8.0, ( 4.4, -3.2, 2.6), (0.86, 0.91, 1.0))
area("Rim_Light",  1000, 2.6, (-0.4,  5.2, 4.0), (1.0, 0.97, 0.92))

# ---- WORLD ----
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.02, 0.02, 0.03, 1.0)
bg.inputs[1].default_value = 0.12

# ---- RENDER ----
sc = bpy.context.scene
try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
ev = sc.eevee
if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 96
if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.filepath = "D:/blender-claude/renders/stomach_03.png"
sc.render.image_settings.file_format = 'PNG'
sc.render.use_compositing = False
try:
    sc.view_settings.view_transform = "AgX"
    for lk in ("AgX - Base Contrast", "AgX - Medium Low Contrast",
               "AgX - Base", "None"):
        try:
            sc.view_settings.look = lk
            break
        except Exception:
            continue
except: pass
sc.view_settings.exposure = -0.25
bpy.ops.render.render(write_still=True)

result = {"saved": sc.render.filepath,
          "spine_samples": len(SPINE),
          "verts": len(obj.data.vertices)}
