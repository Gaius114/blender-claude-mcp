import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# DIVANO COMPONIBILE A L CON CHAISE LONGUE - PELLE COGNAC
# ============================================================

# ---- CLEAR SCENE ----
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.curves):
    for d in list(blk):
        blk.remove(d)

# ---- HELPERS ----
def box(name, cx, cy, cz, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return o

def soft_edges(o, width=0.025, seg=3, subsurf=1):
    b = o.modifiers.new("Bevel", "BEVEL")
    b.width = width; b.segments = seg
    b.limit_method = 'ANGLE'; b.angle_limit = math.radians(30)
    b.profile = 0.5
    if subsurf:
        s = o.modifiers.new("Subsurf", "SUBSURF")
        s.levels = subsurf; s.render_levels = subsurf + 1
    o.data.shade_smooth()

def cushion(name, cx, cy, cz, sx, sy, sz, puff=0.28, prof=0.55):
    o = box(name, cx, cy, cz, sx, sy, sz)
    # bevel + subsurf -> cuscino sodo con spigoli morbidi
    b = o.modifiers.new("Bevel", "BEVEL")
    b.width = min(sx, sy, sz) * puff
    b.segments = 6
    b.limit_method = 'NONE'
    b.profile = prof
    s = o.modifiers.new("Subsurf", "SUBSURF")
    s.levels = 2; s.render_levels = 3
    o.data.shade_smooth()
    return o

def cone_foot(name, cx, cy, cz, r_top, r_bot, h):
    bpy.ops.mesh.primitive_cone_add(
        radius1=r_bot, radius2=r_top, depth=h,
        vertices=16, location=(cx, cy, cz))
    o = bpy.context.active_object
    o.name = name
    b = o.modifiers.new("Bevel", "BEVEL")
    b.width = 0.004; b.segments = 2
    o.data.shade_smooth()
    return o

def assign(o, mat):
    o.data.materials.clear()
    o.data.materials.append(mat)

# ---- MATERIALI ----
def mat_leather():
    m = bpy.data.materials.new("Pelle_Cognac")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out  = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (600, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (200, 0)
    inp = [i.name for i in bsdf.inputs]
    bsdf.inputs['Base Color'].default_value = (0.188, 0.058, 0.020, 1.0)
    bsdf.inputs['Roughness'].default_value  = 0.42
    if 'IOR' in inp: bsdf.inputs['IOR'].default_value = 1.45
    for s in ('Coat Weight', 'Clearcoat'):
        if s in inp: bsdf.inputs[s].default_value = 0.33; break
    for s in ('Coat Roughness', 'Clearcoat Roughness'):
        if s in inp: bsdf.inputs[s].default_value = 0.25; break
    for s in ('Subsurface Weight', 'Subsurface'):
        if s in inp: bsdf.inputs[s].default_value = 0.04; break
    if 'Subsurface Radius' in inp:
        bsdf.inputs['Subsurface Radius'].default_value = (0.25, 0.06, 0.03)
    if 'Subsurface Scale' in inp:
        bsdf.inputs['Subsurface Scale'].default_value = 0.012
    # grana pelle: noise -> bump
    tex = nt.nodes.new('ShaderNodeTexNoise'); tex.location = (-300, -200)
    tex.inputs['Scale'].default_value = 95.0
    tex.inputs['Detail'].default_value = 6.0
    tex.inputs['Roughness'].default_value = 0.7
    bump = nt.nodes.new('ShaderNodeBump'); bump.location = (0, -250)
    bump.inputs['Strength'].default_value = 0.24
    bump.inputs['Distance'].default_value = 0.004
    # pori fini
    tex2 = nt.nodes.new('ShaderNodeTexNoise'); tex2.location = (-300, -480)
    tex2.inputs['Scale'].default_value = 420.0
    tex2.inputs['Detail'].default_value = 3.0
    bump2 = nt.nodes.new('ShaderNodeBump'); bump2.location = (0, -500)
    bump2.inputs['Strength'].default_value = 0.07
    bump2.inputs['Distance'].default_value = 0.0015
    nt.links.new(tex.outputs['Fac'],  bump.inputs['Height'])
    nt.links.new(tex2.outputs['Fac'], bump2.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bump2.inputs['Normal'])
    nt.links.new(bump2.outputs['Normal'], bsdf.inputs['Normal'])
    # variazione di lucentezza non uniforme -> roughness procedurale
    rtex = nt.nodes.new('ShaderNodeTexNoise'); rtex.location = (-300, 200)
    rtex.inputs['Scale'].default_value = 14.0
    rtex.inputs['Detail'].default_value = 4.0
    rramp = nt.nodes.new('ShaderNodeValToRGB'); rramp.location = (-60, 200)
    rramp.color_ramp.elements[0].position = 0.30
    rramp.color_ramp.elements[0].color = (0.34, 0.34, 0.34, 1.0)
    rramp.color_ramp.elements[1].position = 0.75
    rramp.color_ramp.elements[1].color = (0.52, 0.52, 0.52, 1.0)
    nt.links.new(rtex.outputs['Fac'], rramp.inputs['Fac'])
    nt.links.new(rramp.outputs['Color'], bsdf.inputs['Roughness'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m

def mat_metal_dark():
    m = bpy.data.materials.new("Metallo_Scuro")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out  = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (100, 0)
    bsdf.inputs['Base Color'].default_value = (0.05, 0.04, 0.035, 1.0)
    bsdf.inputs['Metallic'].default_value  = 1.0
    bsdf.inputs['Roughness'].default_value = 0.4
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m

def mat_floor():
    m = bpy.data.materials.new("Pavimento")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out  = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (100, 0)
    bsdf.inputs['Base Color'].default_value = (0.12, 0.10, 0.09, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.5
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m

LEATHER = mat_leather()
METAL   = mat_metal_dark()
FLOOR   = mat_floor()

parts_leather = []

# ---- BUILD: PLINTH ----
# corpo principale
p_main = box("Plinth_Main", 0.0, 0.0, 0.27, 2.40, 0.95, 0.30)
soft_edges(p_main, 0.03, 3, 1)
parts_leather.append(p_main)

# chaise (a destra, sporge in avanti -Y)
p_chaise = box("Plinth_Chaise", 1.675, -0.325, 0.27, 0.95, 1.60, 0.30)
soft_edges(p_chaise, 0.03, 3, 1)
parts_leather.append(p_chaise)

# ---- BUILD: BACKREST (inclinato indietro 8 gradi) ----
backrest = box("Backrest", 0.0, 0.375, 0.62, 2.40, 0.20, 0.40)
backrest.rotation_euler[0] = math.radians(-8)
soft_edges(backrest, 0.03, 3, 1)
parts_leather.append(backrest)

# ---- BUILD: ARMREST sinistro ----
arm_l = box("Armrest_L", -1.31, 0.0, 0.37, 0.22, 0.95, 0.50)
soft_edges(arm_l, 0.05, 4, 2)
parts_leather.append(arm_l)

# ---- BUILD: SEAT CUSHIONS ----
seat_z = 0.50
for i, cxp in enumerate((-0.8035, 0.0, 0.8035)):
    c = cushion(f"Seat_Cushion_{i+1}", cxp, -0.05, seat_z, 0.793, 0.85, 0.18,
                puff=0.26, prof=0.52)
    parts_leather.append(c)
# cuscino chaise grande
c_ch = cushion("Seat_Cushion_Chaise", 1.58, -0.325, seat_z, 1.05, 1.50, 0.18,
               puff=0.22, prof=0.50)
parts_leather.append(c_ch)

# ---- BUILD: BACK CUSHIONS ----
for i, cxp in enumerate((-0.8035, 0.0, 0.8035)):
    bc = cushion(f"Back_Cushion_{i+1}", cxp, 0.115, 0.80, 0.80, 0.22, 0.50,
                 puff=0.32, prof=0.58)
    bc.rotation_euler[0] = math.radians(-6)
    parts_leather.append(bc)

# ---- BUILD: FEET ----
feet_pos = [(-1.10, -0.40), (1.10, -0.40), (-1.10, 0.40), (1.10, 0.40),
            (2.00, -1.00), (2.00, 0.30)]
for i, (fx, fy) in enumerate(feet_pos):
    f = cone_foot(f"Foot_{i+1}", fx, fy, 0.06, 0.030, 0.024, 0.12)
    assign(f, METAL)

# ---- MATERIAL: pelle a tutte le parti morbide ----
for o in parts_leather:
    assign(o, LEATHER)

# ---- FLOOR ----
bpy.ops.mesh.primitive_plane_add(size=24, location=(0.3, -0.3, 0.0))
floor = bpy.context.active_object
floor.name = "Floor"
assign(floor, FLOOR)

# ---- CAMERA ----
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.45, -0.30, 0.48))
target = bpy.context.active_object
target.name = "CamTarget"
bpy.ops.object.camera_add(location=(3.6, -4.0, 2.05))
cam = bpy.context.active_object
cam.name = "Camera"
cam.data.lens = 55
tt = cam.constraints.new('TRACK_TO')
tt.target = target
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

# ---- LIGHTS (furniture, scalato) ----
def area(name, energy, size, pos, color=(1.0, 0.96, 0.88)):
    bpy.ops.object.light_add(type='AREA', location=pos)
    L = bpy.context.active_object
    L.name = name
    L.data.energy = energy
    L.data.size = size
    L.data.color = color
    d = Vector((0.4, -0.3, 0.45)) - Vector(pos)
    L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return L

area("Key_Light",   510, 3.6, (-3.0, -3.0, 3.8), (1.0, 0.95, 0.86))
area("Fill_Light",  280, 6.5, ( 3.8, -1.4, 2.4), (0.88, 0.92, 1.0))
area("Rim_Light",   680, 1.5, ( 0.6,  3.6, 3.0), (1.0, 0.96, 0.87))

# ---- WORLD ----
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.02, 0.02, 0.03, 1.0)
bg.inputs[1].default_value = 0.10

# ---- RENDER (EEVEE Next) ----
sc = bpy.context.scene
try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
ev = sc.eevee
if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 96
if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.filepath = "D:/blender-claude/renders/sofa_06.png"
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
sc.view_settings.exposure = -0.35
bpy.ops.render.render(write_still=True)

result = {"saved": sc.render.filepath,
          "objects": len(bpy.data.objects)}
