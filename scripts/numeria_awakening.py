import bpy, bmesh, math, random
from mathutils import Vector
import mathutils.noise as mnoise

# ============================================================
# NUMERIA — "Il risveglio nella stanza grigia"
# Keyframe per cinematic. Mood: pietra grigia + prima luce calda.
# ============================================================
random.seed(3)

# ---- CLEAR ----
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.worlds):
    for d in list(blk):
        try: blk.remove(d)
        except: pass

def box(name, cx, cy, cz, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return o

def capsule(name, p0, p1, r0, r1):
    """tubo conico tra due punti (corpo del Guardiano)."""
    d = (Vector(p1) - Vector(p0))
    h = d.length
    mid = (Vector(p0) + Vector(p1)) / 2
    bpy.ops.mesh.primitive_cone_add(radius1=r0, radius2=r1, depth=h,
                                    vertices=14, location=mid)
    o = bpy.context.active_object
    o.name = name
    z = Vector((0, 0, 1))
    q = z.rotation_difference(d.normalized())
    o.rotation_euler = q.to_euler()
    o.data.shade_smooth()
    return o

def ball(name, p, r):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=r, subdivisions=3,
                                          location=p)
    o = bpy.context.active_object
    o.name = name
    o.data.shade_smooth()
    return o

# ---- STANZA (interno cavo) ----
IW, ID, IH, TH = 4.4, 3.8, 3.0, 0.3
room_parts = []
room_parts.append(box("Pavimento", 0, 0, -TH/2, IW+2*TH, ID+2*TH, TH))
room_parts.append(box("Soffitto",  0, 0, IH+TH/2, IW+2*TH, ID+2*TH, TH))
room_parts.append(box("Muro_N", 0,  ID/2+TH/2, IH/2, IW+2*TH, TH, IH))
room_parts.append(box("Muro_S", 0, -ID/2-TH/2, IH/2, IW+2*TH, TH, IH))
room_parts.append(box("Muro_E",  IW/2+TH/2, 0, IH/2, TH, ID, IH))
room_parts.append(box("Muro_O", -IW/2-TH/2, 0, IH/2, TH, ID, IH))

# fessura verticale alta sul muro OVEST (sinistra, in campo): raggio freddo
slit = box("Cut_Fessura", -IW/2-TH/2, -0.30, IH*0.70, TH*3, 0.24, 1.55)
muroO = room_parts[5]
md = muroO.modifiers.new("Slit", "BOOLEAN")
md.operation = 'DIFFERENCE'; md.object = slit; md.solver = 'EXACT'
bpy.context.view_layer.objects.active = muroO
bpy.ops.object.modifier_apply(modifier="Slit")
bpy.data.objects.remove(slit, do_unlink=True)

# unisci la stanza
for o in room_parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = room_parts[0]
bpy.ops.object.join()
room = bpy.context.active_object
room.name = "Stanza"
# normali verso l'interno non servono: pietra spessa, doppia faccia ok
room.data.shade_smooth()

# qualche detrito a terra
detr = []
for i in range(7):
    rx = random.uniform(-IW/2+0.4, IW/2-0.4)
    ry = random.uniform(-ID/2+0.4, ID/2-0.4)
    if abs(rx) < 1.0 and abs(ry) < 1.0:
        continue
    s = random.uniform(0.06, 0.16)
    r = ball(f"Detrito_{i}", (rx, ry, s*0.5), s)
    r.scale = (random.uniform(0.7,1.3), random.uniform(0.7,1.3),
               random.uniform(0.5,0.9))
    bpy.ops.object.transform_apply(scale=True)
    detr.append(r)

# ---- GUARDIANO (semplice, in penombra, posa di risveglio) ----
gp = []
# bacino
gp.append(ball("G_Bacino", (0.0, 0.15, 0.42), 0.20))
# busto curvo in avanti
gp.append(capsule("G_Busto", (0.0, 0.15, 0.50), (0.0, -0.20, 0.95),
                   0.19, 0.15))
gp.append(ball("G_Petto", (0.0, -0.20, 0.97), 0.155))
# collo + testa che si solleva
gp.append(capsule("G_Collo", (0.0, -0.21, 1.06), (0.0, -0.26, 1.22),
                   0.065, 0.058))
gp.append(ball("G_Testa", (0.0, -0.30, 1.30), 0.165))
# gamba dx: ginocchio a terra
gp.append(capsule("G_CosciaR", (0.12, 0.10, 0.40), (0.20, 0.55, 0.22),
                   0.11, 0.09))
gp.append(capsule("G_StincoR", (0.20, 0.55, 0.20), (0.22, 0.95, 0.10),
                   0.09, 0.06))
# gamba sx: piede appoggiato avanti
gp.append(capsule("G_CosciaL", (-0.14, 0.05, 0.40), (-0.18, -0.30, 0.30),
                   0.11, 0.09))
gp.append(capsule("G_StincoL", (-0.18, -0.30, 0.30), (-0.16, -0.30, 0.0),
                   0.09, 0.06))
# braccia protese in avanti/basso verso il suolo
gp.append(capsule("G_BraccioR", (0.16, -0.18, 0.92), (0.26, -0.55, 0.45),
                   0.07, 0.055))
gp.append(capsule("G_AvambR", (0.26, -0.55, 0.45), (0.30, -0.78, 0.16),
                   0.055, 0.04))
gp.append(capsule("G_BraccioL", (-0.16, -0.18, 0.92), (-0.24, -0.55, 0.45),
                   0.07, 0.055))
gp.append(capsule("G_AvambL", (-0.24, -0.55, 0.45), (-0.28, -0.78, 0.16),
                   0.055, 0.04))
for o in gp:
    o.select_set(True)
bpy.context.view_layer.objects.active = gp[0]
bpy.ops.object.join()
guard = bpy.context.active_object
guard.name = "Guardiano"
guard.data.shade_smooth()

# mani luminose (sfere emissive ai polsi) + posizione luce
hand_R = Vector((0.31, -0.80, 0.14))
hand_L = Vector((-0.29, -0.80, 0.14))
hR = ball("Mano_R", hand_R, 0.075)
hL = ball("Mano_L", hand_L, 0.075)
hand_mid = (hand_R + hand_L) / 2

# ---- MATERIALI ----
def mat_stone():
    m = bpy.data.materials.new("Pietra_Grigia")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location=(700,0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location=(340,0)
    b.inputs['Roughness'].default_value = 0.92
    n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location=(-360,80)
    n1.inputs['Scale'].default_value = 4.5
    n1.inputs['Detail'].default_value = 8.0
    cr = nt.nodes.new('ShaderNodeValToRGB'); cr.location=(-110,80)
    cr.color_ramp.elements[0].color = (0.055,0.056,0.062,1)
    cr.color_ramp.elements[1].color = (0.140,0.142,0.150,1)
    nt.links.new(n1.outputs['Fac'], cr.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
    # bump fratture: due scale
    n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location=(-360,-240)
    n2.inputs['Scale'].default_value = 7.0
    n2.inputs['Detail'].default_value = 9.0
    n3 = nt.nodes.new('ShaderNodeTexNoise'); n3.location=(-360,-470)
    n3.inputs['Scale'].default_value = 35.0
    bp1 = nt.nodes.new('ShaderNodeBump'); bp1.location=(-110,-260)
    bp1.inputs['Strength'].default_value = 0.55
    bp1.inputs['Distance'].default_value = 0.04
    bp2 = nt.nodes.new('ShaderNodeBump'); bp2.location=(120,-300)
    bp2.inputs['Strength'].default_value = 0.22
    bp2.inputs['Distance'].default_value = 0.01
    nt.links.new(n2.outputs['Fac'], bp1.inputs['Height'])
    nt.links.new(bp1.outputs['Normal'], bp2.inputs['Normal'])
    nt.links.new(n3.outputs['Fac'], bp2.inputs['Height'])
    nt.links.new(bp2.outputs['Normal'], b.inputs['Normal'])
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m

def mat_guard():
    m = bpy.data.materials.new("Guardiano_Mat")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location=(400,0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location=(120,0)
    b.inputs['Base Color'].default_value = (0.030,0.031,0.038,1)
    b.inputs['Roughness'].default_value = 0.7
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m

def mat_glow():
    m = bpy.data.materials.new("Luce_Mani")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location=(300,0)
    e = nt.nodes.new('ShaderNodeEmission'); e.location=(60,0)
    e.inputs['Color'].default_value = (1.0, 0.48, 0.16, 1)
    e.inputs['Strength'].default_value = 4.0
    nt.links.new(e.outputs['Emission'], o.inputs['Surface'])
    return m

STONE = mat_stone()
GMAT  = mat_guard()
GLOW  = mat_glow()
room.data.materials.append(STONE)
for d in detr: d.data.materials.append(STONE)
guard.data.materials.append(GMAT)
hR.data.materials.append(GLOW)
hL.data.materials.append(GLOW)

# ---- LUCI ----
# 1) luce calda dalle mani (cuore emotivo)
bpy.ops.object.light_add(type='POINT', location=hand_mid + Vector((0,0,0.05)))
key = bpy.context.active_object
key.name = "Luce_Mani"
key.data.energy = 32
key.data.color = (1.0, 0.58, 0.26)
key.data.shadow_soft_size = 0.28

# 2) raggio freddo dalla fessura OVEST — SPOT che taglia in diagonale
bpy.ops.object.light_add(type='SPOT',
    location=(-IW/2-TH-0.5, -0.30, IH*0.84))
beam = bpy.context.active_object
beam.name = "Raggio_Freddo"
beam.data.energy = 2600
beam.data.color = (0.50, 0.63, 0.97)
beam.data.spot_size = math.radians(38)
beam.data.spot_blend = 0.30
beam.data.shadow_soft_size = 0.04
d = Vector((1.0, 0.06, -0.66))
beam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()

# 3) ambiente freddo bassissimo per non avere nero puro
bpy.ops.object.light_add(type='AREA', location=(-1.8, -1.6, 2.4))
amb = bpy.context.active_object
amb.name = "Ambiente"
amb.data.energy = 11
amb.data.color = (0.38, 0.46, 0.62)
amb.data.size = 4.0

# ---- WORLD (quasi nero, freddo) ----
world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.012, 0.014, 0.020, 1.0)
bg.inputs[1].default_value = 0.05

# ---- VOLUME (pulviscolo per i raggi) ----
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, IH/2))
vol = bpy.context.active_object
vol.name = "Atmosfera"
vol.scale = (IW, ID, IH)
bpy.ops.object.transform_apply(scale=True)
vm = bpy.data.materials.new("Pulviscolo")
vm.use_nodes = True
vnt = vm.node_tree; vnt.nodes.clear()
vo = vnt.nodes.new('ShaderNodeOutputMaterial'); vo.location=(300,0)
pv = vnt.nodes.new('ShaderNodeVolumePrincipled'); pv.location=(0,0)
pv.inputs['Color'].default_value = (0.60, 0.66, 0.80, 1)
pv.inputs['Density'].default_value = 0.14
if 'Anisotropy' in [i.name for i in pv.inputs]:
    pv.inputs['Anisotropy'].default_value = 0.35
vnt.links.new(pv.outputs['Volume'], vo.inputs['Volume'])
vol.data.materials.append(vm)

# ---- CAMERA (intima, bassa) ----
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, -0.28, 0.78))
tgt = bpy.context.active_object; tgt.name = "CamTarget"
bpy.ops.object.camera_add(location=(2.00, 1.75, 0.78))   # dentro la stanza
cam = bpy.context.active_object; cam.name = "Camera"
cam.data.lens = 32
cam.data.dof.use_dof = True
cam.data.dof.focus_object = tgt
cam.data.dof.aperture_fstop = 3.6
tt = cam.constraints.new('TRACK_TO')
tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

# ---- RENDER ----
sc = bpy.context.scene
try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
ev = sc.eevee
if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 128
if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True
for a, v in (('volumetric_tile_size','2'), ('volumetric_samples',128),
             ('volumetric_start',0.05), ('volumetric_end',40.0),
             ('use_volumetric_shadows', True)):
    if hasattr(ev, a):
        try: setattr(ev, a, v)
        except: pass
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.filepath = "D:/blender-claude/renders/numeria_awakening_04.png"
sc.render.image_settings.file_format = 'PNG'
sc.render.use_compositing = False
try:
    sc.view_settings.view_transform = "AgX"
    for lk in ("AgX - Medium High Contrast", "AgX - Base Contrast",
               "AgX - Medium Low Contrast", "None"):
        try: sc.view_settings.look = lk; break
        except Exception: continue
except: pass
sc.view_settings.exposure = -0.2
bpy.ops.render.render(write_still=True)

result = {"saved": sc.render.filepath,
          "room_verts": len(room.data.vertices),
          "guard_verts": len(guard.data.vertices)}
