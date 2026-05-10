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

# Camera: angolo laterale-alto classico, donut visto di 3/4 con lato visibile
r = blender("""
import bpy, math

cam = bpy.data.objects.get("Camera")
if cam:
    for c in list(cam.constraints): cam.constraints.remove(c)

    # Vista bassa: vediamo il lato del donut (dough + drips) e la glassa in cima
    cam.location = (0.20, -0.32, 0.08)
    cam.data.lens = 85
    cam.data.dof.use_dof   = True
    cam.data.dof.focus_distance    = 0.38
    cam.data.dof.aperture_fstop   = 8.0  # molto nitido

    # Track To centro donut leggermente in alto (z=0.02)
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.02))
    tgt = bpy.context.active_object; tgt.name = "T2"
    tt = cam.constraints.new('TRACK_TO')
    tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'

# World molto scuro: sfondo quasi neutro
world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value    = (0.70, 0.68, 0.65, 1.0)
    bg.inputs["Strength"].default_value = 0.25

# Key: riposiziona per colpire il lato del donut
key = bpy.data.objects.get("Key")
if key:
    key.location    = (-0.30, -0.20, 0.35)
    key.data.energy = 25
    key.data.size   = 0.5
    key.data.color  = (1.0, 0.97, 0.88)

fill = bpy.data.objects.get("Fill")
if fill:
    fill.location    = (0.30, 0.10, 0.20)
    fill.data.energy = 8

rim = bpy.data.objects.get("Rim")
if rim:
    rim.location    = (0.0, 0.30, 0.30)
    rim.data.energy = 15

result = {"ok": True}
""", timeout=10)
print("Scene:", r)

render_save("D:/blender-claude/renders/donut_v3.png", w=1280, h=720, exposure=0.15)
