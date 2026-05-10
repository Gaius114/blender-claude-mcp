"""
Bottiglia — Hybrid Workflow Demo
=================================
Phase 1 (Script)    : profilo 2D con bmesh
Phase 2 (bpy.ops)   : Spin 360° attorno a Z (come S nel viewport)
Phase 3 (bpy.ops)   : Edit Mode — loop cuts, inset, extrude
Phase 4 (Script)    : Modifiers (Subsurf, Bevel), materiale vetro
Phase 5 (Visual Loop): Render → Read → analisi → itera
"""

import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r    = json.loads(resp.read().decode())
    if "error" in r:
        print("ERR:", r["error"][:600])
        return None
    return r.get("ok")

def render_save(path, w=1280, h=720, exposure=0.2):
    code = f"""
import bpy, base64, os, tempfile
sc = bpy.context.scene
try: sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "Filmic"
sc.view_settings.look = "High Contrast"
sc.view_settings.exposure = {exposure}
sc.render.use_compositing = False
tmp = tempfile.mktemp(suffix=".png"); sc.render.filepath = tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
os.remove(tmp)
result = {{"b64": b64}}
"""
    r = blender(code, timeout=180)
    if r and "b64" in r:
        img = base64.b64decode(r["b64"])
        with open(path, "wb") as f: f.write(img)
        print(f"  Preview: {path} ({len(img)//1024} KB)")
        return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 + 2 : Profilo → Spin
# ─────────────────────────────────────────────────────────────────────────────
PHASE_1_SPIN = """
import bpy, math, bmesh

# Pulisci
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for m in list(bpy.data.meshes):    bpy.data.meshes.remove(m)
for m in list(bpy.data.materials): bpy.data.materials.remove(m)

# ── Profilo bottiglia di vino (sezione meridiana) ────────────────────────────
# (radius, z)  →  0 = asse centrale, valori reali in metri
# Altezza totale: 30 cm. Diametro max corpo: 8 cm.
profile = [
    # Fondo con punt (concavità tipica bottiglie vino)
    (0.000,  0.018),  # 0  centro fondo (leggermente rialzato = punt)
    (0.012,  0.008),  # 1  interno punt
    (0.030,  0.001),  # 2  bordo punt
    (0.035,  0.004),  # 3  base esterna bassa
    (0.038,  0.010),  # 4  base esterna
    (0.039,  0.022),  # 5  inizio corpo
    # Corpo
    (0.040,  0.055),  # 6  corpo basso
    (0.040,  0.100),  # 7  corpo medio
    (0.040,  0.145),  # 8  punto più largo
    (0.040,  0.172),  # 9  corpo alto
    # Spalla (shoulder) — curva importante del design
    (0.039,  0.185),  # 10 inizio spalla
    (0.036,  0.200),  # 11 spalla
    (0.030,  0.217),  # 12 spalla media
    (0.022,  0.232),  # 13 fine spalla
    # Collo
    (0.018,  0.248),  # 14 collo basso
    (0.017,  0.268),  # 15 collo medio
    (0.017,  0.283),  # 16 collo alto
    # Labbro / imboccatura
    (0.019,  0.292),  # 17 labbro base
    (0.020,  0.297),  # 18 labbro esterno
    (0.018,  0.302),  # 19 imboccatura interna
    (0.000,  0.302),  # 20 centro imboccatura (chiude la superficie)
]

# Crea mesh vuota
mesh = bpy.data.meshes.new("Bottle_mesh")
obj  = bpy.data.objects.new("Bottle", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

# Costruisci profilo con bmesh
bm = bmesh.new()
verts = [bm.verts.new((r, 0.0, z)) for r, z in profile]
bm.verts.ensure_lookup_table()
for i in range(len(verts) - 1):
    bm.edges.new([verts[i], verts[i + 1]])
bm.to_mesh(mesh)
bm.free()
mesh.update()

# ── PHASE 2: SPIN (bpy.ops — stesso operatore di S nel viewport) ─────────────
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')

bpy.ops.mesh.spin(
    steps   = 36,                  # 36 segmenti = 10° ciascuno
    angle   = math.pi * 2,         # 360°
    center  = (0.0, 0.0, 0.0),
    axis    = (0.0, 0.0, 1.0),     # rotazione attorno a Z
)

# Unisci i vertici duplicati alla giuntura (0° = 360°)
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0005)

# Normali coerenti verso l'esterno
bpy.ops.mesh.normals_make_consistent(inside=False)

bpy.ops.object.mode_set(mode='OBJECT')

result = {"verts": len(obj.data.vertices), "faces": len(obj.data.polygons)}
"""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 : Edit Mode ops — loop cuts, selezione chirurgica
# ─────────────────────────────────────────────────────────────────────────────
PHASE_3_EDITMODE = """
import bpy, math, bmesh

obj = bpy.data.objects.get("Bottle")
if not obj:
    result = {"error": "Bottle not found"}
else:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')

    # ── Smooth shading (come Object > Shade Smooth) ──────────────────────────
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.faces_shade_smooth()

    # ── Loop cut aggiuntivo alla spalla per irrigidire la curva ──────────────
    # Seleziona edge loop orizzontale vicino alla spalla z≈0.185
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # Deseleziona tutto
    for v in bm.verts: v.select = False
    for e in bm.edges: e.select = False
    for f in bm.faces: f.select = False
    bm.select_flush(False)

    # Seleziona vertici nella banda z 0.192–0.198 (zona spalla)
    shoulder_verts = [v for v in bm.verts if 0.192 <= v.co.z <= 0.198]
    for v in shoulder_verts:
        v.select = True

    # Seleziona anche gli edge collegati a quei vertici
    for e in bm.edges:
        if e.verts[0].select and e.verts[1].select:
            e.select = True

    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)

    # Subdivide gli edge selezionati → loop cut manuale
    if shoulder_verts:
        bpy.ops.mesh.subdivide(number_cuts=1, smoothness=0.0)

    # ── Seleziona facce del collo, bevel edge ────────────────────────────────
    bpy.ops.mesh.select_all(action='DESELECT')

    # Ri-accedi a bmesh aggiornato
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()

    # Seleziona vertici sulla giuntura spalla-collo (z ~ 0.232)
    for v in bm.verts:
        v.select = abs(v.co.z - 0.232) < 0.004

    bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)

    bpy.ops.object.mode_set(mode='OBJECT')
    result = {
        "verts": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "phase": "edit_mode_done"
    }
"""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 : Modifiers + Materiale Vetro + Scena
# ─────────────────────────────────────────────────────────────────────────────
PHASE_4_MATERIALS = """
import bpy, math

obj = bpy.data.objects.get("Bottle")
bpy.context.view_layer.objects.active = obj

# ── Subdivision Surface (leviga la mesh della spalla e del collo) ────────────
sub = obj.modifiers.new("Subdivision", "SUBSURF")
sub.levels        = 2
sub.render_levels = 3
sub.subdivision_type = 'CATMULL_CLARK'

# ── Bevel automatico sugli spigoli duri ─────────────────────────────────────
bev = obj.modifiers.new("Bevel", "BEVEL")
bev.width         = 0.0015
bev.segments      = 2
bev.limit_method  = 'ANGLE'
bev.angle_limit   = math.radians(35)

# ── Materiale: Vetro Bordeaux (bottiglia vino) ───────────────────────────────
mat = bpy.data.materials.new("GlassBottle")
mat.use_nodes = True
tree  = mat.node_tree
nodes = tree.nodes
links = tree.links
nodes.clear()

out  = nodes.new("ShaderNodeOutputMaterial")
bsdf = nodes.new("ShaderNodeBsdfPrincipled")

# Vetro verde scuro (Bordeaux)
bsdf.inputs["Base Color"].default_value    = (0.018, 0.08, 0.025, 1.0)
bsdf.inputs["Roughness"].default_value     = 0.02
bsdf.inputs["Metallic"].default_value      = 0.0

# Trasmissione
if "Transmission" in bsdf.inputs:
    bsdf.inputs["Transmission"].default_value = 0.95
if "Transmission Weight" in bsdf.inputs:
    bsdf.inputs["Transmission Weight"].default_value = 0.95
if "IOR" in bsdf.inputs:
    bsdf.inputs["IOR"].default_value = 1.52

links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
mat.blend_method = "BLEND"
obj.data.materials.append(mat)

# ── Liquido interno (vino rosso) ─────────────────────────────────────────────
# Mesh separata leggermente più piccola per simulare il liquido
import bmesh

mesh_liq  = bpy.data.meshes.new("Wine_mesh")
obj_liq   = bpy.data.objects.new("Wine", mesh_liq)
bpy.context.collection.objects.link(obj_liq)
bpy.context.view_layer.objects.active = obj_liq
obj_liq.select_set(True)

# Stesso profilo bottle ma: scala radiale 0.96, livello vino z≤0.22 (2/3 pieni)
profile_wine = [
    (0.000, 0.019),
    (0.011, 0.009),
    (0.028, 0.002),
    (0.033, 0.005),
    (0.036, 0.011),
    (0.037, 0.023),
    (0.038, 0.056),
    (0.038, 0.101),
    (0.038, 0.146),
    (0.038, 0.172),
    # Superficie del vino: livello piatto a z=0.220
    (0.038, 0.218),
    (0.000, 0.218),   # chiude in centro
]
bm = bmesh.new()
verts = [bm.verts.new((r, 0.0, z)) for r, z in profile_wine]
bm.verts.ensure_lookup_table()
for i in range(len(verts)-1):
    bm.edges.new([verts[i], verts[i+1]])
bm.to_mesh(mesh_liq); bm.free(); mesh_liq.update()

bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.spin(steps=36, angle=3.14159265*2,
                   center=(0,0,0), axis=(0,0,1))
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0005)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.mesh.faces_shade_smooth()
bpy.ops.object.mode_set(mode='OBJECT')

mat_wine = bpy.data.materials.new("Wine")
mat_wine.use_nodes = True
bw = mat_wine.node_tree.nodes.get("Principled BSDF")
if bw:
    bw.inputs["Base Color"].default_value  = (0.25, 0.01, 0.03, 1.0)
    bw.inputs["Roughness"].default_value   = 0.0
    if "Transmission" in bw.inputs:
        bw.inputs["Transmission"].default_value = 0.75
    if "Transmission Weight" in bw.inputs:
        bw.inputs["Transmission Weight"].default_value = 0.75
    if "IOR" in bw.inputs:
        bw.inputs["IOR"].default_value = 1.34
mat_wine.blend_method = "BLEND"
obj_liq.data.materials.append(mat_wine)

# ── Etichetta (box piatto attorno al corpo) ───────────────────────────────────
bpy.ops.mesh.primitive_cylinder_add(
    radius=0.0408, depth=0.10, vertices=36, location=(0, 0, 0.10))
label = bpy.context.active_object; label.name = "Label"
label_mat = bpy.data.materials.new("Label")
label_mat.use_nodes = True
lb = label_mat.node_tree.nodes.get("Principled BSDF")
if lb:
    lb.inputs["Base Color"].default_value = (0.92, 0.88, 0.78, 1.0)
    lb.inputs["Roughness"].default_value  = 0.8
    lb.inputs["Metallic"].default_value   = 0.0
label.data.materials.append(label_mat)

# Testo etichetta (scritto come scanalatura sul cilindro - leggero offset)
label.location.z += 0.000  # centrato su corpo bottiglia

# ── Sfondo e studio ────────────────────────────────────────────────────────
# Piano riflettente (tavolo)
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
table = bpy.context.active_object; table.name = "Table"
mat_table = bpy.data.materials.new("Table")
mat_table.use_nodes = True
mt = mat_table.node_tree.nodes.get("Principled BSDF")
if mt:
    mt.inputs["Base Color"].default_value = (0.08, 0.06, 0.05, 1.0)
    mt.inputs["Roughness"].default_value  = 0.15
    mt.inputs["Metallic"].default_value   = 0.8
table.data.materials.append(mat_table)

# Piano sfondo
bpy.ops.mesh.primitive_plane_add(size=3, location=(0, 0.8, 0.6))
bg_plane = bpy.context.active_object; bg_plane.name = "BG"
bg_plane.rotation_euler.x = 1.5708
mat_bg = bpy.data.materials.new("BG")
mat_bg.use_nodes = True
mb = mat_bg.node_tree.nodes.get("Principled BSDF")
if mb:
    mb.inputs["Base Color"].default_value = (0.12, 0.12, 0.14, 1.0)
    mb.inputs["Roughness"].default_value  = 1.0
bg_plane.data.materials.append(mat_bg)

# ── Camera product shot ──────────────────────────────────────────────────────
bpy.ops.object.camera_add(location=(0.22, -0.55, 0.20))
cam = bpy.context.active_object; cam.name = "Camera"
cam.rotation_euler = (1.35, 0.0, 0.22)
cam.data.lens = 85            # tele → comprime prospettiva, look professionale
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 0.55
cam.data.dof.aperture_fstop = 2.0
bpy.context.scene.camera = cam

# ── Luci 3 punti (product) ───────────────────────────────────────────────────
# Key (calda, da destra-alto)
bpy.ops.object.light_add(type='AREA', location=(0.5, -0.4, 0.7))
key = bpy.context.active_object; key.name = "Key"
key.data.energy = 40; key.data.size = 0.4
key.data.color  = (1.0, 0.96, 0.88)
key.rotation_euler = (0.8, 0, 0.6)

# Fill (fredda, da sinistra)
bpy.ops.object.light_add(type='AREA', location=(-0.5, -0.3, 0.4))
fill = bpy.context.active_object; fill.name = "Fill"
fill.data.energy = 15; fill.data.size = 0.8
fill.data.color  = (0.75, 0.85, 1.0)

# Rim (retro per trasparenza vetro)
bpy.ops.object.light_add(type='AREA', location=(0.0, 0.5, 0.6))
rim = bpy.context.active_object; rim.name = "Rim"
rim.data.energy = 60; rim.data.size = 0.3
rim.data.color  = (0.95, 0.92, 1.0)
rim.rotation_euler = (-0.7, 0, 0)

# Environment: quasi buio (fa risaltare il vetro)
world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value    = (0.05, 0.05, 0.06, 1.0)
    bg.inputs["Strength"].default_value = 0.15

result = {
    "bottle_verts": len(bpy.data.objects.get("Bottle").data.vertices),
    "bottle_faces": len(bpy.data.objects.get("Bottle").data.polygons),
    "objects": len(bpy.data.objects),
    "phase": "complete"
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# ESECUZIONE
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 55)
print("HYBRID WORKFLOW — Bottiglia di Vino")
print("=" * 55)

print("\n[1/4] Profilo + SPIN (bpy.ops.mesh.spin)...")
r = blender(PHASE_1_SPIN, timeout=20)
print(f"      → {r}")

print("\n[2/4] Edit Mode — smooth, loop cuts chirurgici...")
r = blender(PHASE_3_EDITMODE, timeout=20)
print(f"      → {r}")

print("\n[3/4] Modifiers + Vetro + Vino + Scena...")
r = blender(PHASE_4_MATERIALS, timeout=30)
print(f"      → {r}")

print("\n[4/4] Rendering preview...")
render_save("C:/Users/josia/Downloads/bottle_v1.png", w=1280, h=720, exposure=0.5)

print("\nDone. Analisi visiva in corso...")
