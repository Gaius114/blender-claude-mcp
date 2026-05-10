import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r    = json.loads(resp.read().decode())
    if "error" in r: print("  ERR:", r["error"][:400]); return None
    return r.get("ok")

def render_save(path, w=1920, h=1080, exposure=0.08):
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

# Ricostruisci il materiale icing da zero con colore rosa deciso
r = blender("""
import bpy

# Ricrea icing material completamente (evita problemi di ricerca nodi)
mat = bpy.data.materials.get("Icing")
if mat:
    tree = mat.node_tree
    nodes = tree.nodes; links = tree.links
    nodes.clear()

    out   = nodes.new("ShaderNodeOutputMaterial")
    bsdf  = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    cramp = nodes.new("ShaderNodeValToRGB")
    bump  = nodes.new("ShaderNodeBump")

    # Rosa vivace, stile food photography moderna
    noise.inputs["Scale"].default_value      = 10.0
    noise.inputs["Detail"].default_value     = 3.0
    noise.inputs["Roughness"].default_value  = 0.5

    # Rosa: da rosa acceso a rosa medio
    cramp.color_ramp.elements[0].position = 0.35
    cramp.color_ramp.elements[0].color    = (0.96, 0.42, 0.55, 1.0)  # rosa base
    cramp.color_ramp.elements[1].position = 0.70
    cramp.color_ramp.elements[1].color    = (0.88, 0.28, 0.42, 1.0)  # rosa scuro

    bump.inputs["Strength"].default_value  = 0.15
    bump.inputs["Distance"].default_value  = 0.003

    bsdf.inputs["Roughness"].default_value = 0.18   # glassa lucida
    bsdf.inputs["Metallic"].default_value  = 0.0

    links.new(noise.outputs["Fac"],    cramp.inputs["Fac"])
    links.new(noise.outputs["Fac"],    bump.inputs["Height"])
    links.new(cramp.outputs["Color"],  bsdf.inputs["Base Color"])
    links.new(bump.outputs["Normal"],  bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"],    out.inputs["Surface"])

# Riassegna agli oggetti drip
for obj in bpy.data.objects:
    if obj.name.startswith("Drip_"):
        obj.data.materials.clear()
        obj.data.materials.append(mat)

# Riassegna all'icing
icing = bpy.data.objects.get("Icing")
if icing:
    icing.data.materials.clear()
    icing.data.materials.append(mat)

# Sprinkles: assegna colori vivaci direttamente al mesh base
sprinkle = bpy.data.objects.get("Sprinkle")
palette = [
    ("S_Red",    (0.92, 0.04, 0.04)),
    ("S_Blue",   (0.04, 0.18, 0.92)),
    ("S_Yellow", (0.98, 0.90, 0.02)),
    ("S_Green",  (0.04, 0.75, 0.18)),
    ("S_Purple", (0.58, 0.04, 0.88)),
    ("S_Orange", (0.98, 0.44, 0.02)),
    ("S_Pink",   (0.98, 0.38, 0.68)),
    ("S_Teal",   (0.04, 0.78, 0.72)),
]
if sprinkle:
    sprinkle.data.materials.clear()
    for sname, col in palette:
        m = bpy.data.materials.get(sname) or bpy.data.materials.new(sname)
        m.use_nodes = True
        bs = m.node_tree.nodes.get("Principled BSDF")
        if bs:
            bs.inputs["Base Color"].default_value = (*col, 1.0)
            bs.inputs["Roughness"].default_value  = 0.28
            bs.inputs["Metallic"].default_value   = 0.05
        sprinkle.data.materials.append(m)
    # Assegna materiali ai poligoni con modulo
    for i, poly in enumerate(sprinkle.data.polygons):
        poly.material_index = i % len(palette)

result = {
    "icing_mat_nodes": len(bpy.data.materials.get("Icing").node_tree.nodes) if bpy.data.materials.get("Icing") else 0,
    "sprinkle_mats": len(sprinkle.data.materials) if sprinkle else 0
}
""", timeout=15)
print("Icing rebuilt:", r)

print("Rendering final donut...")
render_save("D:/blender-claude/renders/donut_FINAL.png", w=1920, h=1080, exposure=0.08)
