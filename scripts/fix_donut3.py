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

def render_save(path, w=1280, h=720, exposure=0.2):
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

# Camera piu lontana per vedere il donut intero + icing rosa piu saturo
r = blender("""
import bpy, math

cam = bpy.data.objects.get("Camera")
if cam:
    for c in list(cam.constraints): cam.constraints.remove(c)
    # Piu lontana: vediamo l'intero donut in una bella inquadratura
    cam.location = (0.24, -0.52, 0.10)
    cam.data.lens = 85
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 0.57
    cam.data.dof.aperture_fstop = 5.6

    tgt = bpy.data.objects.get("T2") or bpy.data.objects.get("DonutTarget")
    if tgt:
        tgt.location = (0, 0, 0.025)
    else:
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0.025))
        tgt = bpy.context.active_object; tgt.name = "T3"
    tt = cam.constraints.new('TRACK_TO')
    tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'

# Icing: colore rosa piu saturo e visibile
mat_icing = bpy.data.materials.get("Icing")
if mat_icing:
    for n in mat_icing.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Base Color"].default_value = (0.95, 0.52, 0.60, 1.0)
            n.inputs["Roughness"].default_value  = 0.20
            break

# Drips: stesso materiale icing (rosa)
for obj in bpy.data.objects:
    if obj.name.startswith("Drip_"):
        obj.data.materials.clear()
        obj.data.materials.append(mat_icing)

# Dough: colore piu caldo e visibile
mat_dough = bpy.data.materials.get("Dough")
if mat_dough:
    for n in mat_dough.node_tree.nodes:
        if n.bl_idname == "ShaderNodeValToRGB":
            n.color_ramp.elements[0].color = (0.88, 0.62, 0.32, 1.0)
            n.color_ramp.elements[1].color = (0.48, 0.24, 0.08, 1.0)
            break

# Luci: bilancia per food photography naturale
key = bpy.data.objects.get("Key")
if key:
    key.location    = (-0.35, -0.25, 0.40)
    key.data.energy = 30
    key.data.size   = 0.65

fill = bpy.data.objects.get("Fill")
if fill:
    fill.location    = (0.35, 0.15, 0.25)
    fill.data.energy = 10

world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value    = (0.75, 0.73, 0.70, 1.0)
    bg.inputs["Strength"].default_value = 0.30

result = {"ok": True}
""", timeout=10)
print("Fixes:", r)

render_save("D:/blender-claude/renders/donut_v4.png", w=1280, h=720, exposure=0.1)
