import urllib.request, json, base64

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request("http://localhost:7234/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r = json.loads(resp.read().decode())
    if "error" in r:
        print("ERR:", r["error"][:400])
        return None
    return r.get("ok")

def render_save(path, w=1280, h=720):
    code = f"""
import bpy, base64, os, tempfile
sc = bpy.context.scene
try: sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x={w}; sc.render.resolution_y={h}
sc.view_settings.view_transform="Filmic"
sc.view_settings.look="Medium High Contrast"
sc.view_settings.exposure=0.2
sc.render.use_compositing=False
tmp=tempfile.mktemp(suffix=".png"); sc.render.filepath=tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64=base64.b64encode(f.read()).decode()
os.remove(tmp)
result={{"b64":b64}}
"""
    r = blender(code, timeout=180)
    if r and "b64" in r:
        img = base64.b64decode(r["b64"])
        with open(path, "wb") as f:
            f.write(img)
        print(f"Saved {path} ({len(img)//1024}KB)")
        return True
    return False


BUILD_CODE = """
import bpy, math, bmesh

# Pulisci
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for m in list(bpy.data.meshes):    bpy.data.meshes.remove(m)
for m in list(bpy.data.materials): bpy.data.materials.remove(m)

# ---- HELPERS ----
def assign_mat(obj, mat):
    if obj.data.materials: obj.data.materials[0] = mat
    else: obj.data.materials.append(mat)

def smooth_shade(obj):
    for p in obj.data.polygons: p.use_smooth = True
    obj.data.update()

def add_bevel(obj, amount=0.02, segments=2):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = amount
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)
    return mod

def box(name, x, y, z, sx, sy, sz, mat=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z))
    o = bpy.context.active_object
    o.name = name; o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if mat: assign_mat(o, mat)
    return o

def cyl(name, x, y, z, r, h, verts=32, mat=None):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=r, depth=h, vertices=verts, location=(x, y, z))
    o = bpy.context.active_object; o.name = name
    smooth_shade(o)
    if mat: assign_mat(o, mat)
    return o

# ---- MATERIALI ----
def mat_pbr(name, color, roughness=0.5, metallic=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    m.node_tree.nodes.clear()
    bsdf = m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    out  = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    m.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["Metallic"].default_value   = metallic
    return m

def mat_wood(name, color=(0.45, 0.28, 0.12)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    tree = m.node_tree; tree.nodes.clear()
    out   = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf  = tree.nodes.new("ShaderNodeBsdfPrincipled")
    wave  = tree.nodes.new("ShaderNodeTexWave")
    cramp = tree.nodes.new("ShaderNodeValToRGB")
    wave.wave_type = "BANDS"
    wave.inputs["Scale"].default_value      = 8
    wave.inputs["Distortion"].default_value = 2.5
    wave.inputs["Detail"].default_value     = 4.0
    c2 = tuple(min(1, c + 0.18) for c in color)
    cramp.color_ramp.elements[0].color = (*color, 1.0)
    cramp.color_ramp.elements[1].color = (*c2,   1.0)
    tree.links.new(wave.outputs["Color"],  cramp.inputs["Fac"])
    tree.links.new(cramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.65
    tree.links.new(bsdf.outputs["BSDF"],   out.inputs["Surface"])
    return m

mat_steel = mat_pbr("Steel",  (0.75, 0.75, 0.78), roughness=0.15, metallic=1.0)
mat_oak   = mat_wood("Oak",   (0.62, 0.38, 0.18))
mat_fabric= mat_pbr("Fabric", (0.22, 0.35, 0.52), roughness=0.90)
mat_floor = mat_pbr("Floor",  (0.88, 0.85, 0.80), roughness=0.30)
mat_wall  = mat_pbr("Wall",   (0.96, 0.95, 0.93), roughness=0.85)
mat_lamp_m= mat_pbr("LampMt", (0.12, 0.12, 0.14), roughness=0.18, metallic=1.0)
mat_shade = mat_pbr("Shade",  (0.95, 0.90, 0.80), roughness=0.70)

# ---- SEDIA MODERNA (bevel + smooth) ----
seat = box("Seat", 0, 0, 0.46, 0.52, 0.50, 0.09, mat_fabric)
add_bevel(seat, 0.018, 3); smooth_shade(seat)

back = box("Back", 0, 0.23, 0.78, 0.46, 0.09, 0.62, mat_fabric)
add_bevel(back, 0.015, 3); smooth_shade(back)

for side, sx in [("L", -0.21), ("R", 0.21)]:
    gf = box(f"Leg_F{side}", sx, -0.18, 0.225, 0.022, 0.022, 0.45, mat_steel)
    add_bevel(gf, 0.004, 2); smooth_shade(gf)
    gf.rotation_euler.x = math.radians(4)

    gb = box(f"Leg_B{side}", sx, 0.20, 0.225, 0.022, 0.022, 0.45, mat_steel)
    add_bevel(gb, 0.004, 2); smooth_shade(gb)
    gb.rotation_euler.x = math.radians(-4)

    ch = box(f"Conn{side}", sx, 0.01, 0.05, 0.022, 0.43, 0.022, mat_steel)
    add_bevel(ch, 0.003, 2); smooth_shade(ch)

# ---- TAVOLO ----
tw, td, th = 1.4, 0.7, 0.74
top = box("Table_Top", 1.8, 0, th + 0.02, tw, td, 0.04, mat_oak)
add_bevel(top, 0.006, 2); smooth_shade(top)

for lx, ly in [(-tw/2+0.06, -td/2+0.06), (tw/2-0.06, -td/2+0.06),
               (-tw/2+0.06,  td/2-0.06), (tw/2-0.06,  td/2-0.06)]:
    leg = box(f"TL_{lx:.2f}", 1.8 + lx, ly, th/2 - 0.02, 0.05, 0.05, th - 0.04, mat_steel)
    add_bevel(leg, 0.004, 2); smooth_shade(leg)

# Traversa
tr = box("Table_Bar", 1.8, 0, 0.12, 1.26, 0.04, 0.04, mat_steel)
add_bevel(tr, 0.003, 2); smooth_shade(tr)

# ---- LAMPADA DA PAVIMENTO ----
lx, ly = -2.0, 0.8
bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.07, vertices=32,
                                     location=(lx, ly, 0.035))
base = bpy.context.active_object; base.name = "Lamp_Base"
assign_mat(base, mat_lamp_m); smooth_shade(base); add_bevel(base, 0.01, 2)

pole = cyl("Lamp_Pole", lx, ly, 0.85, 0.014, 1.52, 16, mat_lamp_m)

bpy.ops.mesh.primitive_cone_add(radius1=0.24, radius2=0.07, depth=0.30,
                                 vertices=32, location=(lx, ly, 1.66))
shade_obj = bpy.context.active_object; shade_obj.name = "Lamp_Shade"
assign_mat(shade_obj, mat_shade); smooth_shade(shade_obj)

bpy.ops.object.light_add(type='POINT', location=(lx, ly, 1.56))
bulb = bpy.context.active_object; bulb.name = "Lamp_Bulb"
bulb.data.energy = 180
bulb.data.color  = (1.0, 0.92, 0.75)
bulb.data.shadow_soft_size = 0.07

# ---- AMBIENTE ----
floor = box("Floor", 0, 0, -0.01, 9, 9, 0.02, mat_floor)
add_bevel(floor, 0.003, 1)
wall = box("Wall_Back", 0, 2.5, 2.0, 9, 0.1, 4.5, mat_wall)

# ---- CAMERA ----
bpy.ops.object.camera_add(location=(5, -6, 3.2))
cam = bpy.context.active_object; cam.name = "Camera"
cam.rotation_euler = (math.radians(68), 0, math.radians(40))
cam.data.lens = 50
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 6.5
cam.data.dof.aperture_fstop = 1.8
bpy.context.scene.camera = cam

# ---- LUCI 3-POINT ----
bpy.ops.object.light_add(type='AREA', location=(4, -5, 6))
key = bpy.context.active_object; key.name = "Key_Light"
key.data.energy = 700; key.data.size = 2.5
key.data.color  = (1.0, 0.95, 0.88)
key.rotation_euler = (math.radians(45), 0, math.radians(45))

bpy.ops.object.light_add(type='AREA', location=(-5, -3, 4))
fill = bpy.context.active_object; fill.name = "Fill_Light"
fill.data.energy = 200; fill.data.size = 6
fill.data.color  = (0.75, 0.85, 1.0)

bpy.ops.object.light_add(type='AREA', location=(0, 5, 5))
rim = bpy.context.active_object; rim.name = "Rim_Light"
rim.data.energy = 450; rim.data.size = 1.5
rim.data.color  = (0.90, 0.95, 1.0)
rim.rotation_euler = (math.radians(-45), 0, 0)

# World: scuro (interior shot)
world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.07, 0.07, 0.09, 1.0)
    bg.inputs["Strength"].default_value = 0.2

result = {
    "objects":   len(bpy.data.objects),
    "materials": len(bpy.data.materials),
}
"""

print("Building scene...")
r = blender(BUILD_CODE, timeout=30)
print("Result:", r)

print("Rendering...")
render_save("C:/Users/josia/Downloads/skill_demo_chair.png", 1280, 720)
