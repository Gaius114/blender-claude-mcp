import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())
    if "error" in r: print("  ERR:", r["error"][:800]); return None
    return r.get("ok")

def render_save(path, w=1920, h=1080, exposure=0.09):
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

r = blender(
    # Apple: move to front-right area, clearly visible peeking above rim
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a: a.location=(0.06, -0.09, 0.142)\n"
    "sa=bpy.data.objects.get('AppleStem')\n"
    "if sa: sa.location=(0.057, -0.09, 0.208)\n"
    # Pear: undo the 0.82 scale, make it bigger again, move to left
    "pear=bpy.data.objects.get('Pear')\n"
    "if pear:\n"
    "    pear.scale=(1.18, 1.18, 1.18)\n"    # upscale back
    "    pear.location=(0.0, 0.0, -0.215)\n"  # lower because it's bigger
    "sp=bpy.data.objects.get('PearStem')\n"
    "if sp: sp.location=(0.107, -0.047, 0.285)\n"
    # Banana: shift slightly right so apple is visible
    "b=bpy.data.objects.get('Banana')\n"
    "if b: b.location=(0.04, 0.0, -0.080)\n"
    "result={'ok':True}\n",
    timeout=10
)
print("Reposition:", r)

render_save("D:/blender-claude/renders/basket_v6.png")
