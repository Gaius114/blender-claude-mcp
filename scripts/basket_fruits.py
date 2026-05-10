import urllib.request, json, base64, os

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r    = json.loads(resp.read().decode())
    if "error" in r: print("  ERR:", r["error"][:800]); return None
    return r.get("ok")

def render_save(path, w=1280, h=720, exposure=0.1):
    code = f"""
import bpy, base64, os, tempfile
sc = bpy.context.scene
try: sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x={w}; sc.render.resolution_y={h}
sc.view_settings.view_transform="Filmic"
sc.view_settings.look="Medium High Contrast"
sc.view_settings.exposure={exposure}
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
        with open(path, "wb") as f: f.write(img)
        print(f"  Saved: {path} ({len(img)//1024}KB)")

# ══════════════════════════════════════════════════════════════
# PHASE 2 — APPLE + PEAR
# ══════════════════════════════════════════════════════════════
r = blender("""
import bpy, bmesh, math

def new_obj(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj

def smooth(obj):
    for p in obj.data.polygons: p.use_smooth = True
    obj.data.update()

def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

def noise_mat(name, c1, c2, roughness=0.4, scale=8.0, bump_str=0.25):
    m = bpy.data.materials.new(name)
    m.use_nodes = True; t = m.node_tree; t.nodes.clear()
    out  = t.nodes.new('ShaderNodeOutputMaterial')
    bsdf = t.nodes.new('ShaderNodeBsdfPrincipled')
    ns   = t.nodes.new('ShaderNodeTexNoise')
    cr   = t.nodes.new('ShaderNodeValToRGB')
    bmp  = t.nodes.new('ShaderNodeBump')
    ns.inputs['Scale'].default_value = scale
    ns.inputs['Detail'].default_value = 5.0
    cr.color_ramp.elements[0].color = (*c1, 1.0)
    cr.color_ramp.elements[1].color = (*c2, 1.0)
    bmp.inputs['Strength'].default_value = bump_str
    t.links.new(ns.outputs['Fac'], cr.inputs['Fac'])
    t.links.new(ns.outputs['Fac'], bmp.inputs['Height'])
    t.links.new(cr.outputs['Color'], bsdf.inputs['Base Color'])
    t.links.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Roughness'].default_value = roughness
    t.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m

mat_stem = bpy.data.materials.new("Stem")
mat_stem.use_nodes = True
mat_stem.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.20,0.13,0.05,1)
mat_stem.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.92

# ── APPLE ──────────────────────────────────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.068, segments=32, ring_count=20,
                                      location=(-0.07, 0.05, 0.285))
apple = bpy.context.active_object; apple.name = "Apple"
apple.scale.z = 0.85
bpy.ops.object.transform_apply(scale=True)
smooth(apple)
mat_apple = noise_mat("Apple", (0.85,0.05,0.04),(0.52,0.12,0.02), roughness=0.22, scale=9, bump_str=0.2)
assign(apple, mat_apple)

# Dent at top
bm = bmesh.new(); bm.from_mesh(apple.data)
bm.verts.ensure_lookup_table()
bm.verts.sort(key=lambda v: -v.co.z)
for i, v in enumerate(bm.verts):
    if i == 0:
        v.co.z -= 0.018
    elif i < 6 and v.co.z > 0.03:
        v.co.z -= 0.007
bm.to_mesh(apple.data); bm.free(); apple.data.update()

# Apple stem
bpy.ops.mesh.primitive_cylinder_add(radius=0.005, depth=0.035,
                                     location=(-0.074, 0.05, 0.360))
stem_a = bpy.context.active_object; stem_a.name = "AppleStem"
stem_a.rotation_euler = (0.18, 0.12, 0)
assign(stem_a, mat_stem); smooth(stem_a)

# ── PEAR ───────────────────────────────────────────────────────
pear_profile = [
    (0.000,0.000),(0.030,0.004),(0.055,0.018),(0.068,0.046),
    (0.070,0.080),(0.062,0.110),(0.048,0.132),(0.032,0.148),
    (0.028,0.160),(0.034,0.175),(0.040,0.190),(0.036,0.206),
    (0.022,0.218),(0.010,0.226),(0.000,0.230)
]
segments = 28
px_off, py_off, pz_off = 0.09, -0.04, 0.19

bm = bmesh.new()
rings = []
for r_val, z_val in pear_profile:
    ring = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        ring.append(bm.verts.new((
            px_off + r_val * math.cos(angle),
            py_off + r_val * math.sin(angle),
            pz_off + z_val
        )))
    rings.append(ring)
bm.verts.ensure_lookup_table()
for ri in range(len(rings)-1):
    r0, r1 = rings[ri], rings[ri+1]
    for j in range(segments):
        nj = (j+1) % segments
        bm.faces.new([r0[j], r0[nj], r1[nj], r1[j]])
# bottom cap
c_bot = bm.verts.new((px_off, py_off, pz_off - 0.002))
for j in range(segments):
    nj = (j+1) % segments
    bm.faces.new([c_bot, rings[0][nj], rings[0][j]])
bm.normal_update()
mesh = bpy.data.meshes.new("Pear_mesh")
bm.to_mesh(mesh); bm.free()
pear = new_obj("Pear", mesh); smooth(pear)
mat_pear = noise_mat("Pear", (0.70,0.80,0.12),(0.52,0.65,0.06), roughness=0.38, scale=6)
assign(pear, mat_pear)

# Pear stem
bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=0.028,
                                     location=(0.09, -0.04, 0.432))
stem_p = bpy.context.active_object; stem_p.name = "PearStem"
stem_p.rotation_euler = (-0.12, 0.18, 0)
assign(stem_p, mat_stem); smooth(stem_p)

result = {"apple": apple.name, "pear": pear.name}
""", timeout=20)
print("Apple+Pear:", r)

# ══════════════════════════════════════════════════════════════
# PHASE 3 — BANANA
# ══════════════════════════════════════════════════════════════
r = blender("""
import bpy, bmesh, math
from mathutils import Vector, Matrix

def new_obj(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj

def smooth(obj):
    for p in obj.data.polygons: p.use_smooth = True
    obj.data.update()

def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

# Banana: tube following circular arc, tapering at tips
arc_R    = 0.095      # radius of curvature (gives ~18cm arc)
n_sec    = 22         # sections along arc
n_circ   = 10         # vertices per cross-section
arc_span = math.radians(130)

# Banana center in scene
bx_c, by_c, bz_c = -0.04, -0.10, 0.215

bm = bmesh.new()
all_rings = []

for i in range(n_sec + 1):
    t      = i / n_sec
    theta  = -arc_span/2 + t * arc_span   # angle along arc

    # Position on arc (arc in local XZ plane, centered at (0,0,arc_R))
    lx = arc_R * math.sin(theta)
    lz = arc_R * (1.0 - math.cos(theta))  # 0 at both ends

    # Tangent direction
    tx =  math.cos(theta)
    tz =  math.sin(theta)

    # Cross-section axes perpendicular to tangent
    # local_x: in arc plane, perpendicular to tangent = (-sin, 0, cos)
    ax = Vector((-math.sin(theta), 0.0, math.cos(theta)))
    ay = Vector((0.0, 1.0, 0.0))   # Y is always horizontal

    # Taper: full at center, pointed at tips — quadratic
    taper = 1.0 - (abs(t - 0.5) * 2.0) ** 1.8
    taper = max(0.04, taper)
    rx = 0.023 * taper   # width
    ry = 0.017 * taper   # depth

    # Banana cross-section: slightly triangular (3 ridges) via 10 points
    ring = []
    for j in range(n_circ):
        angle = 2 * math.pi * j / n_circ
        # Add slight triangular ridge effect
        ridge = 0.006 * taper * max(0, math.cos(3 * angle))
        r_eff_x = rx + ridge
        r_eff_y = ry + ridge * 0.5
        # Point in local cross-section plane
        pt_local = r_eff_x * math.cos(angle) * ax + r_eff_y * math.sin(angle) * ay

        # Arc position
        arc_pt = Vector((lx, 0.0, lz)) + pt_local

        # Rotate banana 25 deg around Z to lie diagonally in basket
        rot_z = math.radians(25)
        gx = arc_pt.x * math.cos(rot_z) - arc_pt.y * math.sin(rot_z)
        gy = arc_pt.x * math.sin(rot_z) + arc_pt.y * math.cos(rot_z)
        gz = arc_pt.z

        ring.append(bm.verts.new((bx_c + gx, by_c + gy, bz_c + gz)))
    all_rings.append(ring)

bm.verts.ensure_lookup_table()
for i in range(len(all_rings) - 1):
    r0, r1 = all_rings[i], all_rings[i+1]
    for j in range(n_circ):
        nj = (j+1) % n_circ
        bm.faces.new([r0[j], r0[nj], r1[nj], r1[j]])

# Caps
bm.faces.new(list(reversed(all_rings[0])))
bm.faces.new(all_rings[-1])
bm.normal_update()

mesh = bpy.data.meshes.new("Banana_mesh")
bm.to_mesh(mesh); bm.free()
banana = new_obj("Banana", mesh)
smooth(banana)

# Banana material
mat_b = bpy.data.materials.new("Banana")
mat_b.use_nodes = True; t = mat_b.node_tree; t.nodes.clear()
out  = t.nodes.new('ShaderNodeOutputMaterial')
bsdf = t.nodes.new('ShaderNodeBsdfPrincipled')
ns   = t.nodes.new('ShaderNodeTexNoise')
cr   = t.nodes.new('ShaderNodeValToRGB')
bmp  = t.nodes.new('ShaderNodeBump')
ns.inputs['Scale'].default_value = 5.0
ns.inputs['Detail'].default_value = 3.0
cr.color_ramp.elements[0].color = (0.98, 0.90, 0.08, 1.0)
cr.color_ramp.elements[1].color = (0.90, 0.78, 0.03, 1.0)
bmp.inputs['Strength'].default_value = 0.15
t.links.new(ns.outputs['Fac'], cr.inputs['Fac'])
t.links.new(ns.outputs['Fac'], bmp.inputs['Height'])
t.links.new(cr.outputs['Color'], bsdf.inputs['Base Color'])
t.links.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
bsdf.inputs['Roughness'].default_value = 0.40
t.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
assign(banana, mat_b)

result = {"banana_verts": len(banana.data.vertices), "banana_faces": len(banana.data.polygons)}
""", timeout=20)
print("Banana:", r)

# ══════════════════════════════════════════════════════════════
# PHASE 4 — PINEAPPLE
# ══════════════════════════════════════════════════════════════
r = blender("""
import bpy, bmesh, math

def new_obj(name, mesh):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj

def smooth(obj):
    for p in obj.data.polygons: p.use_smooth = True
    obj.data.update()

def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

mat_leaf = bpy.data.materials.new("PineLeaf")
mat_leaf.use_nodes = True
mat_leaf.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.06,0.38,0.06,1)
mat_leaf.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.65

# PINEAPPLE BODY — tapered cylinder with diamond-scale bump
bm = bmesh.new()
n_h = 20; n_v = 32
r0_pine = 0.058; r_top_pine = 0.048; h_pine = 0.195
ox, oy, oz = 0.00, 0.06, 0.195   # position (back-center of basket)

all_rings = []
for i in range(n_h + 1):
    t = i / n_h
    z = oz + t * h_pine
    r = r0_pine + (r_top_pine - r0_pine) * t
    ring = []
    for j in range(n_v):
        ang = 2 * math.pi * j / n_v
        ring.append(bm.verts.new((ox + r*math.cos(ang), oy + r*math.sin(ang), z)))
    all_rings.append(ring)
bm.verts.ensure_lookup_table()
for i in range(n_h):
    for j in range(n_v):
        nj = (j+1) % n_v
        bm.faces.new([all_rings[i][j], all_rings[i][nj], all_rings[i+1][nj], all_rings[i+1][j]])

# Bottom cap
c_bot = bm.verts.new((ox, oy, oz))
for j in range(n_v):
    nj = (j+1) % n_v
    bm.faces.new([c_bot, all_rings[0][nj], all_rings[0][j]])
# Top dome
c_top = bm.verts.new((ox, oy, oz + h_pine + 0.018))
for j in range(n_v):
    nj = (j+1) % n_v
    bm.faces.new([c_top, all_rings[-1][j], all_rings[-1][nj]])

bm.normal_update()
mesh = bpy.data.meshes.new("Pineapple_mesh")
bm.to_mesh(mesh); bm.free()
pineapple = new_obj("Pineapple", mesh)
smooth(pineapple)

# Pineapple material — diamond scale pattern
mat_pine = bpy.data.materials.new("Pineapple")
mat_pine.use_nodes = True; t = mat_pine.node_tree; t.nodes.clear()
out   = t.nodes.new('ShaderNodeOutputMaterial')
bsdf  = t.nodes.new('ShaderNodeBsdfPrincipled')
coord = t.nodes.new('ShaderNodeTexCoord')
ns    = t.nodes.new('ShaderNodeTexNoise')
voro  = t.nodes.new('ShaderNodeTexVoronoi')
cr    = t.nodes.new('ShaderNodeValToRGB')
bmp   = t.nodes.new('ShaderNodeBump')
mix_c = t.nodes.new('ShaderNodeMixRGB')
# Voronoi for diamond scale pattern
voro.voronoi_dimensions = '3D'
voro.inputs['Scale'].default_value = 22.0
# Color variation with noise
ns.inputs['Scale'].default_value = 4.0
cr.color_ramp.elements[0].color = (0.70, 0.42, 0.05, 1.0)
cr.color_ramp.elements[1].color = (0.88, 0.65, 0.12, 1.0)
bmp.inputs['Strength'].default_value = 2.0
bmp.inputs['Distance'].default_value = 0.010
mix_c.blend_type = 'MULTIPLY'; mix_c.inputs['Fac'].default_value = 0.6
t.links.new(coord.outputs['Generated'], voro.inputs['Vector'])
t.links.new(coord.outputs['Generated'], ns.inputs['Vector'])
t.links.new(ns.outputs['Fac'], cr.inputs['Fac'])
t.links.new(voro.outputs['Distance'], bmp.inputs['Height'])
t.links.new(cr.outputs['Color'], mix_c.inputs[1])
t.links.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
t.links.new(mix_c.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.78
t.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
assign(pineapple, mat_pine)

# PINEAPPLE CROWN — 12 spiky leaves
n_leaves = 12
crown_z = oz + h_pine + 0.018
for li in range(n_leaves):
    ang = 2 * math.pi * li / n_leaves
    leaf_len = 0.10 + (li % 3) * 0.025
    tilt = 0.30 + (li % 2) * 0.15   # outward tilt

    bm = bmesh.new()
    n_pts = 6
    base_r = 0.022
    base_verts = []
    for j in range(n_pts):
        a = 2 * math.pi * j / n_pts
        base_verts.append(bm.verts.new((
            ox + base_r * math.cos(a),
            oy + base_r * math.sin(a),
            crown_z
        )))
    tip = bm.verts.new((
        ox + math.cos(ang) * math.sin(tilt) * leaf_len,
        oy + math.sin(ang) * math.sin(tilt) * leaf_len,
        crown_z + math.cos(tilt) * leaf_len
    ))
    bm.verts.ensure_lookup_table()
    for j in range(n_pts):
        nj = (j+1) % n_pts
        bm.faces.new([base_verts[j], base_verts[nj], tip])
    bm.normal_update()
    mesh = bpy.data.meshes.new(f"Leaf{li}_mesh")
    bm.to_mesh(mesh); bm.free()
    leaf = new_obj(f"PineLeaf{li:02d}", mesh)
    smooth(leaf); assign(leaf, mat_leaf)

result = {"pineapple_verts": len(pineapple.data.vertices), "leaves": n_leaves}
""", timeout=25)
print("Pineapple:", r)

# ══════════════════════════════════════════════════════════════
# PHASE 5 — CAMERA + LIGHTS + TABLE
# ══════════════════════════════════════════════════════════════
r = blender("""
import bpy, math

# Table surface
bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, -0.01))
table = bpy.context.active_object; table.name = "Table"
mat_table = bpy.data.materials.new("TableWood")
mat_table.use_nodes = True; t = mat_table.node_tree; t.nodes.clear()
out  = t.nodes.new('ShaderNodeOutputMaterial')
bsdf = t.nodes.new('ShaderNodeBsdfPrincipled')
wave = t.nodes.new('ShaderNodeTexWave')
cr   = t.nodes.new('ShaderNodeValToRGB')
bmp  = t.nodes.new('ShaderNodeBump')
wave.wave_type = 'BANDS'; wave.inputs['Scale'].default_value = 6.0
wave.inputs['Distortion'].default_value = 2.0; wave.inputs['Detail'].default_value = 3.0
cr.color_ramp.elements[0].color = (0.42, 0.25, 0.10, 1.0)
cr.color_ramp.elements[1].color = (0.60, 0.38, 0.18, 1.0)
bmp.inputs['Strength'].default_value = 0.2
t.links.new(wave.outputs['Color'], cr.inputs['Fac'])
t.links.new(wave.outputs['Color'], bmp.inputs['Height'])
t.links.new(cr.outputs['Color'], bsdf.inputs['Base Color'])
t.links.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
bsdf.inputs['Roughness'].default_value = 0.55
t.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
table.data.materials.append(mat_table)

# Camera — 3/4 view, slightly elevated
bpy.ops.object.camera_add(location=(0.52, -0.58, 0.52))
cam = bpy.context.active_object; cam.name = "Camera"
cam.data.lens = 85
bpy.context.scene.camera = cam
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.28))
tgt = bpy.context.active_object; tgt.name = "CamTarget"
tt = cam.constraints.new('TRACK_TO')
tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 0.88
cam.data.dof.aperture_fstop = 6.3

# Key light — warm, from upper-left
bpy.ops.object.light_add(type='AREA', location=(-0.55, -0.60, 0.90))
key = bpy.context.active_object; key.name = "Key"
key.data.energy = 90; key.data.size = 0.75
key.data.color = (1.0, 0.95, 0.82)
key.rotation_euler = (math.radians(38), 0, math.radians(-38))

# Fill light — cool, from right
bpy.ops.object.light_add(type='AREA', location=(0.65, 0.25, 0.55))
fill = bpy.context.active_object; fill.name = "Fill"
fill.data.energy = 28; fill.data.size = 1.4
fill.data.color = (0.78, 0.85, 1.0)

# Rim — from behind
bpy.ops.object.light_add(type='AREA', location=(0.05, 0.65, 0.70))
rim = bpy.context.active_object; rim.name = "Rim"
rim.data.energy = 45; rim.data.size = 0.5
rim.data.color = (0.95, 1.0, 0.92)
rim.rotation_euler = (math.radians(-48), 0, 0)

# World
world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.82, 0.79, 0.76, 1.0)
    bg.inputs["Strength"].default_value = 0.45

result = {"camera": cam.name, "lights": ["Key","Fill","Rim"]}
""", timeout=15)
print("Camera+Lights:", r)

print("\nRendering fruit basket...")
render_save("D:/blender-claude/renders/basket_v1.png", w=1280, h=720, exposure=0.12)
