import urllib.request, json, base64, os, random

BLENDER_URL = "http://localhost:7234"
RENDERS_DIR = "D:/blender-claude/renders"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r    = json.loads(resp.read().decode())
    if "error" in r: print("  ERR:", r["error"][:400]); return None
    return r.get("ok")

def render_save(filename, w=1280, h=720, exposure=0.3):
    path = f"{RENDERS_DIR}/{filename}"
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
        print(f"  Render saved: {path} ({len(img)//1024} KB)")

# Fix 1: Camera — angolo 3/4 classico food photography, meno DOF
r = blender("""
import bpy, math

cam = bpy.data.objects.get("Camera")
if cam:
    for c in list(cam.constraints): cam.constraints.remove(c)
    # Vista 3/4: vediamo la glassa sopra + i drips sul lato
    cam.location = (0.22, -0.30, 0.18)
    cam.rotation_euler = (math.radians(68), 0, math.radians(38))
    cam.data.lens = 85
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 0.36
    cam.data.dof.aperture_fstop = 5.6  # meno blur = tutto piu a fuoco

# Key light piu forte per vedere bene icing e dough
key = bpy.data.objects.get("Key")
if key:
    key.data.energy = 50
    key.location = (-0.35, -0.25, 0.45)

# Fill
fill = bpy.data.objects.get("Fill")
if fill:
    fill.data.energy = 15

result = {"camera": "fixed"}
""", timeout=10)
print("Camera:", r)

# Fix 2: Sprinkle con colori multipli assegnati casualmente
r = blender("""
import bpy, random, math
random.seed(99)

sprinkle = bpy.data.objects.get("Sprinkle")
if sprinkle:
    # Assegna tutti i materiali colore all'oggetto sprinkle
    colors = [
        ("Spr_Red",    (0.85, 0.08, 0.08)),
        ("Spr_Blue",   (0.10, 0.20, 0.85)),
        ("Spr_Yellow", (0.95, 0.85, 0.05)),
        ("Spr_Green",  (0.08, 0.60, 0.15)),
        ("Spr_Purple", (0.50, 0.10, 0.75)),
        ("Spr_Orange", (0.95, 0.45, 0.05)),
        ("Spr_White",  (0.98, 0.96, 0.94)),
        ("Spr_Pink",   (0.95, 0.50, 0.65)),
    ]
    sprinkle.data.materials.clear()
    for sname, scolor in colors:
        mat = bpy.data.materials.get(sname)
        if not mat:
            mat = bpy.data.materials.new(sname)
            mat.use_nodes = True
            bs = mat.node_tree.nodes.get("Principled BSDF")
            if bs:
                bs.inputs["Base Color"].default_value = (*scolor, 1.0)
                bs.inputs["Roughness"].default_value  = 0.35
                bs.inputs["Metallic"].default_value   = 0.05
        sprinkle.data.materials.append(mat)

    # Assegna materiali ai poligoni casualmente
    for poly in sprinkle.data.polygons:
        poly.material_index = random.randint(0, len(colors)-1)

result = {"sprinkle_mats": len(sprinkle.data.materials) if sprinkle else 0}
""", timeout=10)
print("Sprinkles:", r)

# Fix 3: La glassa non copre tutto — abbassa soglia taglio
r = blender("""
import bpy, bmesh
icing = bpy.data.objects.get("Icing")
if icing:
    # Icing: abbassa leggermente per coprire meglio la parte superiore
    icing.location.z = 0.005

    # Aggiorna shrinkwrap offset (piu aderente)
    for mod in icing.modifiers:
        if mod.type == "SHRINKWRAP":
            mod.offset = 0.0008

result = {"icing": "adjusted"}
""", timeout=10)
print("Icing:", r)

print("Rendering v2...")
render_save("donut_v2.png", w=1280, h=720, exposure=0.45)
