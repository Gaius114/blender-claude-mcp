import urllib.request, json, sys

def send(endpoint, payload, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f'http://localhost:7234{endpoint}', data=data,
        headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode())

# ── STEP 1: MODELING ─────────────────────────────────────────────────────────
code = """
import bpy, math

# Pulisci scena
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def box(name, x, y, z, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x,y,z))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return o

# FONDAMENTA
box('Foundation', 0, 0, -0.15, 12, 8, 0.3)

# PIANO TERRA
box('GroundFloor', 0, 0, 1.5, 12, 8, 3.0)

# PIANO PRIMO (rientrato, volume asimmetrico moderno)
box('FirstFloor', -0.5, 0, 4.65, 11, 7.5, 3.0)

# GARAGE (corpo laterale basso)
box('Garage', 4.5, 0, 1.0, 3, 8, 2.0)

# TETTO PIANO - corpo principale
box('Roof_Main', -0.5, 0, 6.28, 11.4, 8.2, 0.4)

# PENSILINA GARAGE
box('Garage_Roof', 4.5, 0, 2.12, 3.4, 8.4, 0.2)

# TERRAZZA (lastra)
box('Terrace_Slab', -0.5, -1.5, 3.12, 11, 5, 0.15)

# FINESTRE PIANO TERRA (fronte)
for i, (wx, wz) in enumerate([(-3.5, 1.2), (0.0, 1.2), (-3.5, 2.4), (0.0, 2.4)]):
    box(f'Win_GF_{i}', wx, -4.01, wz, 1.4, 0.05, 0.85)

# FINESTRE GRANDI PIANO PRIMO (fronte)
for i, (wx, wz) in enumerate([(-3.0, 4.9), (0.8, 4.9)]):
    box(f'Win_FF_{i}', wx, -4.01, wz, 2.4, 0.05, 1.7)

# PORTA INGRESSO
box('Door_Main', -5.5, -4.01, 0.95, 1.1, 0.05, 1.9)

# PORTA GARAGE
box('Door_Garage', 4.5, -4.01, 1.0, 2.6, 0.05, 1.75)

# COLONNE INGRESSO
for cx in [-6.2, -4.8]:
    box(f'Column_{int(abs(cx))}', cx, -4.3, 1.55, 0.2, 0.2, 3.1)

# SCALINI INGRESSO
for i in range(3):
    box(f'Step_{i}', -5.5, -4.45 - i*0.38, i*0.15, 1.6, 0.38, 0.15)

# PARAPETTO TERRAZZA (fronte)
box('Parapet_Front', -0.5, -4.15, 3.5, 11.0, 0.12, 0.9)
box('Parapet_Left',  -5.6, -1.65, 3.5, 0.12, 5.0, 0.9)
box('Parapet_Right',  4.6, -1.65, 3.5, 0.12, 5.0, 0.9)

# CAMERA
bpy.ops.object.camera_add(location=(18, -20, 10))
cam = bpy.context.active_object
cam.name = 'Camera_Main'
cam.rotation_euler = (1.1, 0, 0.7)
bpy.context.scene.camera = cam

# SOLE
bpy.ops.object.light_add(type='SUN', location=(10, -10, 15))
sun = bpy.context.active_object
sun.name = 'Sun'
sun.data.energy = 3.0
sun.rotation_euler = (0.8, 0, 0.5)

result = {
    "objects": len(bpy.data.objects),
    "meshes": len([o for o in bpy.data.objects if o.type == 'MESH']),
    "status": "modeling_complete"
}
"""

print("== STEP 1: MODELING ==")
r = send('/execute', {'code': code})
print(r)
