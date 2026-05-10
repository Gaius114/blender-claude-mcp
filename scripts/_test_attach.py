"""
Test del sistema attach_to / attach_bounds / world_bounds
Crea due oggetti semplici e verifica che si tocchino con precisione.
"""
import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"
def blender(code, timeout=30):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    if "error" in r: print("ERR:", r["error"][:600]); return None
    return r.get("ok")

# ── Clear ─────────────────────────────────────────────────────────────
blender("import bpy; bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(); result={'ok':True}")

# ── Definisco le funzioni attach nel contesto Blender ──────────────────
ATTACH_LIB = """
import bpy
from mathutils import Vector

def local_to_world(obj, p_local):
    bpy.context.view_layer.update()
    return obj.matrix_world @ Vector(p_local)

def world_to_local(obj, p_world):
    bpy.context.view_layer.update()
    return obj.matrix_world.inverted() @ Vector(p_world)

def world_bounds(obj):
    bpy.context.view_layer.update()
    verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
    mn = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
    mx = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
    return {'min': mn, 'max': mx, 'center': (mn+mx)/2, 'size': mx-mn}

def attach_to(obj_b, pt_b_local, obj_a, pt_a_local, align=False, gap=0.0, gap_axis=None):
    bpy.context.view_layer.update()
    p_target = obj_a.matrix_world @ Vector(pt_a_local)

    if align:
        obj_b.rotation_mode = 'QUATERNION'
        obj_b.rotation_quaternion = obj_a.matrix_world.to_quaternion()
        bpy.context.view_layer.update()

    p_now = obj_b.matrix_world @ Vector(pt_b_local)
    delta_world = p_target - p_now

    if gap != 0.0:
        if gap_axis is not None:
            delta_world += Vector(gap_axis).normalized() * gap
        elif delta_world.length > 1e-10:
            delta_world += delta_world.normalized() * gap

    if obj_b.parent:
        delta = obj_b.parent.matrix_world.inverted().to_3x3() @ delta_world
    else:
        delta = delta_world

    obj_b.location = obj_b.location + delta
    bpy.context.view_layer.update()

    p_a_f = obj_a.matrix_world @ Vector(pt_a_local)
    p_b_f = obj_b.matrix_world @ Vector(pt_b_local)
    return (p_b_f - p_a_f).length

def attach_bounds(obj_b, face_b, obj_a, face_a, gap=0.0):
    AXIS   = {'top':2,'bottom':2,'front':1,'back':1,'right':0,'left':0}
    IS_MAX = {'top':True,'right':True,'back':True,'bottom':False,'left':False,'front':False}
    bpy.context.view_layer.update()
    ax = AXIS[face_a]
    va = [obj_a.matrix_world @ v.co for v in obj_a.data.vertices]
    vb = [obj_b.matrix_world @ v.co for v in obj_b.data.vertices]
    ext_a = max(v[ax] for v in va) if IS_MAX[face_a] else min(v[ax] for v in va)
    ext_b = max(v[ax] for v in vb) if IS_MAX[face_b] else min(v[ax] for v in vb)
    delta_ax = ext_a - ext_b + gap * (1 if IS_MAX[face_a] else -1)
    if obj_b.parent:
        world_d = [0,0,0]; world_d[ax] = delta_ax
        local_d = obj_b.parent.matrix_world.inverted().to_3x3() @ Vector(world_d)
        obj_b.location += local_d
    else:
        obj_b.location[ax] += delta_ax
    bpy.context.view_layer.update()
    vb2 = [obj_b.matrix_world @ v.co for v in obj_b.data.vertices]
    ext_b2 = max(v[ax] for v in vb2) if IS_MAX[face_b] else min(v[ax] for v in vb2)
    return abs(ext_b2 - ext_a)
"""

# ── TEST 1: attach_to — cilindro poggia sopra un cubo ─────────────────
r = blender(ATTACH_LIB + """
# Cubo base a z=0 (dimensioni 0.1x0.1x0.1, origin al centro)
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0.05))
cube = bpy.context.active_object; cube.name = 'Cube'

# Cilindro posizionato a caso
bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.06, location=(0.5, 0.3, 0.7))
cyl = bpy.context.active_object; cyl.name = 'Cyl'

# Punto di attacco: TOP del cubo (z_local = +0.05 perché size=0.1, origin al centro)
# Punto di attacco: BOTTOM del cilindro (z_local = -0.03 perché depth=0.06)
residual = attach_to(cyl, (0, 0, -0.03), cube, (0, 0, 0.05))

# Verifica
b_cyl = world_bounds(cyl)
b_cube = world_bounds(cube)
result = {
    'test': 'attach_to basic',
    'residual_m': residual,
    'residual_um': round(residual * 1e6, 3),
    'cube_top_z': round(b_cube['max'].z, 6),
    'cyl_bot_z':  round(b_cyl['min'].z, 6),
    'gap_z':      round(b_cyl['min'].z - b_cube['max'].z, 8),
}
""", timeout=10)
print("TEST 1 (attach_to basic):", r)

# ── TEST 2: attach_bounds — stessa cosa ma usando facce bbox ───────────
r = blender(ATTACH_LIB + """
# Stesso setup ma usa attach_bounds
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0.3, 0, 0.05))
cube = bpy.context.active_object; cube.name = 'Cube2'

bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.06, location=(-0.9, 1.1, 3.3))
cyl = bpy.context.active_object; cyl.name = 'Cyl2'

residual = attach_bounds(cyl, 'bottom', cube, 'top')

b_cyl = world_bounds(cyl)
b_cube = world_bounds(cube)
result = {
    'test': 'attach_bounds',
    'residual_m': residual,
    'residual_um': round(residual * 1e6, 3),
    'cube_top_z': round(b_cube['max'].z, 6),
    'cyl_bot_z':  round(b_cyl['min'].z, 6),
}
""", timeout=10)
print("TEST 2 (attach_bounds):", r)

# ── TEST 3: attach_to con oggetto RUOTATO ─────────────────────────────
r = blender(ATTACH_LIB + """
import math
# Cubo ruotato di 45° attorno a Z
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0.05))
cube = bpy.context.active_object; cube.name = 'CubeRot'
cube.rotation_euler = (0, 0, math.radians(45))
bpy.context.view_layer.update()

# Sfera da attaccare al top del cubo
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.04, location=(5, 5, 5))
sphere = bpy.context.active_object; sphere.name = 'Sphere'

# Top del cubo ruotato (in local space: z_local = +0.05, x=y=0)
# Bottom della sfera (in local space: z_local = -0.04)
residual = attach_to(sphere, (0, 0, -0.04), cube, (0, 0, 0.05))

b_sph = world_bounds(sphere)
b_cube = world_bounds(cube)
result = {
    'test': 'attach_to rotated object',
    'residual_um': round(residual * 1e6, 3),
    'cube_top_z_world': round(b_cube['max'].z, 6),
    'sphere_bot_z_world': round(b_sph['min'].z, 6),
    'gap_um': round((b_sph['min'].z - b_cube['max'].z) * 1e6, 3),
}
""", timeout=10)
print("TEST 3 (attach_to rotated):", r)

# ── TEST 4: gap positivo (oggetto distanziato) ────────────────────────
r = blender(ATTACH_LIB + """
bpy.ops.mesh.primitive_cube_add(size=0.1, location=(0, 0, 0.05))
cube = bpy.context.active_object; cube.name = 'CubeGap'

bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.06, location=(0, 0, 10))
cyl = bpy.context.active_object; cyl.name = 'CylGap'

gap = 0.005  # 5mm di gap
residual = attach_to(cyl, (0,0,-0.03), cube, (0,0,0.05), gap=gap, gap_axis=(0,0,1))

b_cyl  = world_bounds(cyl)
b_cube = world_bounds(cube)
actual_gap = b_cyl['min'].z - b_cube['max'].z
result = {
    'test': 'attach_to with gap',
    'requested_gap_mm': gap * 1000,
    'actual_gap_mm': round(actual_gap * 1000, 4),
    'error_um': round((actual_gap - gap) * 1e6, 3),
}
""", timeout=10)
print("TEST 4 (gap):", r)

print("\nAll tests done.")
