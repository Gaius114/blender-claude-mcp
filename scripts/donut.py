"""
Blender Donut — Hybrid Workflow
================================
Ispirato al tutorial Blenderguru (Andrew Price).

Phase 1 (Script)     : Torus base del donut
Phase 2 (bpy.ops)    : Edit Mode — irregolarita organiche, bump
Phase 3 (Script)     : Icing — torus modificato con Shrinkwrap + drips
Phase 4 (bpy.ops)    : Geometry Nodes — sprinkles procedurali
Phase 5 (Script)     : Materiali realistici (dough + icing + sprinkles)
Phase 6 (Visual Loop): Render → analisi → itera
"""

import urllib.request, json, base64, os

BLENDER_URL = "http://localhost:7234"
RENDERS_DIR = "D:/blender-claude/renders"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r    = json.loads(resp.read().decode())
    if "error" in r:
        print("  ERR:", r["error"][:500])
        return None
    return r.get("ok")

def render_save(filename, w=1280, h=720, exposure=0.3, look="High Contrast"):
    path = f"{RENDERS_DIR}/{filename}"
    code = f"""
import bpy, base64, os, tempfile
sc = bpy.context.scene
try: sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "Filmic"
sc.view_settings.look = "{look}"
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
        os.makedirs(RENDERS_DIR, exist_ok=True)
        with open(path, "wb") as f: f.write(img)
        print(f"  Render: {path} ({len(img)//1024} KB)")
        return path
    return None

# =============================================================================
# PHASE 1: DONUT BASE — Torus + deformazione organica
# =============================================================================
PHASE1 = """
import bpy, math, bmesh, random
random.seed(42)

# Pulisci scena
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for m in list(bpy.data.meshes):    bpy.data.meshes.remove(m)
for m in list(bpy.data.materials): bpy.data.materials.remove(m)

# ── Torus base (corpo del donut) ──────────────────────────────────────────────
# major_radius = raggio del cerchio centrale
# minor_radius = raggio del tubo (spessore)
bpy.ops.mesh.primitive_torus_add(
    major_radius    = 0.09,   # 9cm di raggio
    minor_radius    = 0.035,  # 3.5cm di spessore
    major_segments  = 48,
    minor_segments  = 16,
    location        = (0, 0, 0)
)
donut = bpy.context.active_object
donut.name = "Donut"

# ── Phase 2: Edit Mode — rendi il donut IRREGOLARE (non perfettamente tondo) ──
# Il tutorial di Blenderguru insegna proprio questo: nessun cibo e' perfetto.
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(donut.data)

# Sposta vertici casualmente per look organico (simula effetto Grab/Inflate)
for v in bm.verts:
    offset_strength = 0.004  # 4mm di variazione massima
    v.co.x += random.uniform(-offset_strength, offset_strength)
    v.co.y += random.uniform(-offset_strength, offset_strength)
    v.co.z += random.uniform(-offset_strength * 0.5, offset_strength * 0.8)

# Appiattisci leggermente il fondo (il donut poggia su un piano)
for v in bm.verts:
    if v.co.z < -0.025:
        v.co.z = v.co.z * 0.4  # schiaccia verso il basso

bmesh.update_edit_mesh(donut.data)
bpy.ops.object.mode_set(mode='OBJECT')

# ── Smooth shading ─────────────────────────────────────────────────────────────
bpy.ops.object.shade_smooth()

# ── Subdivision Surface: leviga ma mantiene le irregolarita ───────────────────
sub = donut.modifiers.new("Subdivision", "SUBSURF")
sub.levels        = 2
sub.render_levels = 3
sub.subdivision_type = 'CATMULL_CLARK'

result = {
    "donut_verts": len(donut.data.vertices),
    "donut_faces": len(donut.data.polygons),
    "phase": "donut_base_done"
}
"""

# =============================================================================
# PHASE 2: ICING — glassa che cola sul donut
# =============================================================================
PHASE2 = """
import bpy, math, bmesh, random
random.seed(7)

donut = bpy.data.objects.get("Donut")

# ── Crea il torus dell'icing (leggermente piu grande, solo meta superiore) ────
bpy.ops.mesh.primitive_torus_add(
    major_radius   = 0.09,
    minor_radius   = 0.036,
    major_segments = 48,
    minor_segments = 16,
    location       = (0, 0, 0.003)  # leggermente sopra il donut
)
icing = bpy.context.active_object
icing.name = "Icing"

# ── Taglia via la meta inferiore dell'icing ────────────────────────────────────
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(icing.data)
bm.verts.ensure_lookup_table()

# Rimuovi vertici sotto il piano z=0 del donut (la glassa sta sopra)
verts_to_delete = [v for v in bm.verts if v.co.z < -0.001]
bmesh.ops.delete(bm, geom=verts_to_delete, context='VERTS')
bmesh.update_edit_mesh(icing.data)
bpy.ops.object.mode_set(mode='OBJECT')

# ── Shrinkwrap: la glassa aderisce perfettamente alla superficie del donut ────
sw = icing.modifiers.new("Shrinkwrap", "SHRINKWRAP")
sw.target       = donut
sw.wrap_method  = 'TARGET_PROJECT'
sw.offset       = 0.001  # 1mm sopra la superficie

# ── Smooth shading ─────────────────────────────────────────────────────────────
bpy.ops.object.shade_smooth()

# ── SubSurf per levigare la glassa ────────────────────────────────────────────
sub = icing.modifiers.new("Subdivision", "SUBSURF")
sub.levels        = 2
sub.render_levels = 3

# ── Drips: aggiungi "gocce" che colano sul lato ───────────────────────────────
# Creiamo piccole sfere/gocce attorno al bordo dell'icing
def make_drip(name, angle_deg, drip_len=0.015, drip_r=0.007):
    angle = math.radians(angle_deg)
    # Posizione sul bordo esterno del donut (r=0.09+0.035 = bordo)
    bx = 0.095 * math.cos(angle)
    by = 0.095 * math.sin(angle)

    # Goccia allungata (icosfera schiacciata verticalmente)
    bpy.ops.mesh.primitive_ico_sphere_add(
        radius=drip_r, subdivisions=2,
        location=(bx, by, -0.01 - drip_len * 0.5)
    )
    drip = bpy.context.active_object
    drip.name = name
    drip.scale.z = 1.0 + drip_len * 15  # allungata verso il basso
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    return drip

# Aggiungi 8 gocce casuali
drip_angles = [12, 45, 78, 130, 175, 220, 280, 330]
drip_lengths = [0.018, 0.025, 0.012, 0.022, 0.016, 0.020, 0.014, 0.019]
drips = []
for i, (a, l) in enumerate(zip(drip_angles, drip_lengths)):
    d = make_drip(f"Drip_{i}", a, drip_len=l, drip_r=0.006 + random.uniform(-0.001, 0.002))
    drips.append(d)

result = {
    "icing_verts": len(icing.data.vertices),
    "drips": len(drips),
    "phase": "icing_done"
}
"""

# =============================================================================
# PHASE 3: SPRINKLES — Geometry Nodes scatter sulla glassa
# =============================================================================
PHASE3 = """
import bpy, math, random
random.seed(13)

icing = bpy.data.objects.get("Icing")

# Crea un singolo sprinkle (cilindretto con capsule ends)
bpy.ops.mesh.primitive_cylinder_add(
    radius=0.002, depth=0.010, vertices=8, location=(999, 999, 999))
sprinkle_base = bpy.context.active_object
sprinkle_base.name = "Sprinkle_Base"

# Caps arrotondate
for dz in [0.005, -0.005]:
    bpy.ops.mesh.primitive_ico_sphere_add(
        radius=0.002, subdivisions=1, location=(999, 999, 999 + dz))
    cap = bpy.context.active_object
    cap.name = f"Cap_{dz}"
    cap.parent = sprinkle_base

# Unisci tutto in un oggetto
bpy.ops.object.select_all(action='DESELECT')
sprinkle_base.select_set(True)
for child in sprinkle_base.children:
    child.select_set(True)
bpy.context.view_layer.objects.active = sprinkle_base
bpy.ops.object.join()
sprinkle_base = bpy.context.active_object
sprinkle_base.name = "Sprinkle"
bpy.ops.object.shade_smooth()

# ── Geometry Nodes sull'icing: scatter sprinkles ──────────────────────────────
mod = icing.modifiers.new("Sprinkles_GN", "NODES")
ng  = bpy.data.node_groups.new("SprinkleScatter", "GeometryNodeTree")
mod.node_group = ng

gn_nodes = ng.nodes
gn_links = ng.links

# Interfaccia I/O
if hasattr(ng, "interface"):
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="INPUT",  socket_type="NodeSocketGeometry")

in_node  = gn_nodes.new("NodeGroupInput")
out_node = gn_nodes.new("NodeGroupOutput")

# Distribute Points on Faces
dist = gn_nodes.new("GeometryNodeDistributePointsOnFaces")
dist.distribute_method = "RANDOM"
dist.inputs["Density"].default_value = 3000.0  # sprinkles per m^2

# Instance on Points
inst = gn_nodes.new("GeometryNodeInstanceOnPoints")

# Object Info per lo sprinkle
obj_info = gn_nodes.new("GeometryNodeObjectInfo")
obj_info.inputs["Object"].default_value = sprinkle_base

# Rotate Instance (random rotation)
rot = gn_nodes.new("GeometryNodeRotateInstances")

# Random rotation input
rand_rot = gn_nodes.new("FunctionNodeRandomValue")
rand_rot.data_type = "FLOAT_VECTOR"
rand_rot.inputs["Min"].default_value = (0, 0, 0)
rand_rot.inputs["Max"].default_value = (6.28, 6.28, 6.28)

# Realize Instances
realize = gn_nodes.new("GeometryNodeRealizeInstances")

# Collega i nodi
gn_links.new(in_node.outputs[0],           dist.inputs["Mesh"])
gn_links.new(dist.outputs["Points"],       inst.inputs["Points"])
gn_links.new(obj_info.outputs["Geometry"], inst.inputs["Instance"])
gn_links.new(dist.outputs["Normal"],       inst.inputs["Rotation"])
gn_links.new(inst.outputs["Instances"],    rot.inputs["Instances"])
gn_links.new(rand_rot.outputs[0],          rot.inputs["Rotation"])
gn_links.new(rot.outputs["Instances"],     realize.inputs["Geometry"])
gn_links.new(realize.outputs["Geometry"],  out_node.inputs[0])

result = {"sprinkles_gn": "ok", "phase": "sprinkles_done"}
"""

# =============================================================================
# PHASE 4: MATERIALI
# =============================================================================
PHASE4 = """
import bpy

# ── Materiale Donut (impasto, dough) ─────────────────────────────────────────
mat_dough = bpy.data.materials.new("Dough")
mat_dough.use_nodes = True
tree = mat_dough.node_tree; tree.nodes.clear()

out   = tree.nodes.new("ShaderNodeOutputMaterial")
bsdf  = tree.nodes.new("ShaderNodeBsdfPrincipled")
noise = tree.nodes.new("ShaderNodeTexNoise")
cramp = tree.nodes.new("ShaderNodeValToRGB")
bump  = tree.nodes.new("ShaderNodeBump")

# Colore impasto: marrone dorato
noise.inputs["Scale"].default_value      = 18.0
noise.inputs["Detail"].default_value     = 8.0
noise.inputs["Roughness"].default_value  = 0.7
noise.inputs["Distortion"].default_value = 0.4

# ColorRamp: variazione dal beige al marrone tostato
cramp.color_ramp.elements[0].position = 0.3
cramp.color_ramp.elements[0].color    = (0.90, 0.65, 0.35, 1.0)  # beige
cramp.color_ramp.elements[1].position = 0.75
cramp.color_ramp.elements[1].color    = (0.52, 0.28, 0.10, 1.0)  # marrone tostato

bump.inputs["Strength"].default_value = 0.6
bump.inputs["Distance"].default_value = 0.005

bsdf.inputs["Roughness"].default_value = 0.85
bsdf.inputs["Specular IOR Level"].default_value = 0.1 if "Specular IOR Level" in [i.name for i in bsdf.inputs] else 0

tree.links.new(noise.outputs["Fac"],   cramp.inputs["Fac"])
tree.links.new(noise.outputs["Fac"],   bump.inputs["Height"])
tree.links.new(cramp.outputs["Color"], bsdf.inputs["Base Color"])
tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
tree.links.new(bsdf.outputs["BSDF"],   out.inputs["Surface"])

donut = bpy.data.objects.get("Donut")
if donut: donut.data.materials.append(mat_dough)

# ── Materiale Icing (glassa rosa) ─────────────────────────────────────────────
mat_icing = bpy.data.materials.new("Icing")
mat_icing.use_nodes = True
ti = mat_icing.node_tree; ti.nodes.clear()

out_i  = ti.nodes.new("ShaderNodeOutputMaterial")
bsdf_i = ti.nodes.new("ShaderNodeBsdfPrincipled")
noise_i= ti.nodes.new("ShaderNodeTexNoise")
cramp_i= ti.nodes.new("ShaderNodeValToRGB")

# Rosa chiaro con leggera variazione
noise_i.inputs["Scale"].default_value     = 12.0
noise_i.inputs["Detail"].default_value    = 4.0
noise_i.inputs["Roughness"].default_value = 0.5

cramp_i.color_ramp.elements[0].color = (0.98, 0.68, 0.72, 1.0)  # rosa base
cramp_i.color_ramp.elements[1].color = (0.95, 0.58, 0.65, 1.0)  # rosa scuro

bsdf_i.inputs["Roughness"].default_value = 0.25  # glassa lucida
bsdf_i.inputs["Metallic"].default_value  = 0.0

ti.links.new(noise_i.outputs["Fac"],   cramp_i.inputs["Fac"])
ti.links.new(cramp_i.outputs["Color"], bsdf_i.inputs["Base Color"])
ti.links.new(bsdf_i.outputs["BSDF"],   out_i.inputs["Surface"])

icing = bpy.data.objects.get("Icing")
if icing: icing.data.materials.append(mat_icing)

# Stesso materiale per le gocce
for obj in bpy.data.objects:
    if obj.name.startswith("Drip_"):
        obj.data.materials.append(mat_icing)

# ── Materiali Sprinkles (colorati) ────────────────────────────────────────────
sprinkle_colors = [
    ("Spr_Red",    (0.80, 0.08, 0.08)),
    ("Spr_Blue",   (0.08, 0.15, 0.75)),
    ("Spr_Yellow", (0.95, 0.85, 0.05)),
    ("Spr_Green",  (0.08, 0.55, 0.12)),
    ("Spr_Purple", (0.45, 0.08, 0.70)),
    ("Spr_Orange", (0.95, 0.45, 0.05)),
]
for sname, scolor in sprinkle_colors:
    ms = bpy.data.materials.new(sname)
    ms.use_nodes = True
    bs = ms.node_tree.nodes.get("Principled BSDF")
    if bs:
        bs.inputs["Base Color"].default_value = (*scolor, 1.0)
        bs.inputs["Roughness"].default_value  = 0.35
        bs.inputs["Metallic"].default_value   = 0.1

# ── Piano + sfondo ─────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=1.5, location=(0, 0, -0.038))
plate = bpy.context.active_object; plate.name = "Plate"
mat_plate = bpy.data.materials.new("Plate")
mat_plate.use_nodes = True
bp = mat_plate.node_tree.nodes.get("Principled BSDF")
if bp:
    bp.inputs["Base Color"].default_value = (0.95, 0.94, 0.90, 1.0)
    bp.inputs["Roughness"].default_value  = 0.15
    bp.inputs["Metallic"].default_value   = 0.05
plate.data.materials.append(mat_plate)

result = {
    "materials": len(bpy.data.materials),
    "phase": "materials_done"
}
"""

# =============================================================================
# PHASE 5: CAMERA + LUCI — setup fotografico food
# =============================================================================
PHASE5 = """
import bpy, math

# ── Camera: angolo food photography (dall'alto-lato, classico per cibo) ──────
bpy.ops.object.camera_add(location=(0.18, -0.28, 0.22))
cam = bpy.context.active_object; cam.name = "Camera"

# Punta al centro del donut
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.01))
tgt = bpy.context.active_object; tgt.name = "DonutTarget"
tt = cam.constraints.new('TRACK_TO')
tt.target     = tgt
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis    = 'UP_Y'

cam.data.lens = 85
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 0.30
cam.data.dof.aperture_fstop = 2.8
bpy.context.scene.camera = cam

# ── Key light (soffice, da sinistra-alto — simula finestra) ──────────────────
bpy.ops.object.light_add(type='AREA', location=(-0.4, -0.2, 0.5))
key = bpy.context.active_object; key.name = "Key"
key.data.energy = 30
key.data.size   = 0.6
key.data.color  = (1.0, 0.97, 0.90)
key.rotation_euler = (math.radians(45), 0, math.radians(-45))

# ── Fill (riflettore opposto, freddo) ────────────────────────────────────────
bpy.ops.object.light_add(type='AREA', location=(0.4, 0.1, 0.3))
fill = bpy.context.active_object; fill.name = "Fill"
fill.data.energy = 8
fill.data.size   = 1.0
fill.data.color  = (0.80, 0.88, 1.0)

# ── Rim / backlight per esaltare la glassa ───────────────────────────────────
bpy.ops.object.light_add(type='AREA', location=(0.05, 0.3, 0.35))
rim = bpy.context.active_object; rim.name = "Rim"
rim.data.energy = 20
rim.data.size   = 0.3
rim.data.color  = (1.0, 0.95, 0.85)
rim.rotation_euler = (math.radians(-40), 0, 0)

# ── World: sfondo caldo quasi bianco ─────────────────────────────────────────
world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value    = (0.85, 0.82, 0.78, 1.0)
    bg.inputs["Strength"].default_value = 0.4

result = {"scene_ready": True, "objects": len(bpy.data.objects)}
"""

# =============================================================================
# ESECUZIONE
# =============================================================================
print("=" * 55)
print("BLENDER DONUT — Hybrid Workflow")
print("=" * 55)

print("\n[1/5] Torus base + deformazione organica...")
r = blender(PHASE1, timeout=20)
print(f"      {r}")

print("\n[2/5] Icing (glassa) + drips...")
r = blender(PHASE2, timeout=20)
print(f"      {r}")

print("\n[3/5] Sprinkles (Geometry Nodes)...")
r = blender(PHASE3, timeout=20)
print(f"      {r}")

print("\n[4/5] Materiali (dough, icing, sprinkles)...")
r = blender(PHASE4, timeout=20)
print(f"      {r}")

print("\n[5/5] Camera + luci food photography...")
r = blender(PHASE5, timeout=15)
print(f"      {r}")

print("\nRendering preview...")
render_save("donut_v1.png", w=1280, h=720, exposure=0.4, look="High Contrast")

print("\nDone. Analisi visiva in corso...")
