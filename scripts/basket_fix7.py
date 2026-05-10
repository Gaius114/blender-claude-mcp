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

# Apple: local vertex offset = +0.342 from loc.z
# Want apple world top = 0.21 (peek 2cm above rim at 0.19)
# loc.z = 0.21 - 0.342 = -0.132
# Apple world center = -0.132 + 0.285 = 0.153 ✓
r = blender(
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a: a.location=(-0.08, -0.06, -0.132)\n"   # front-left, peeking above rim
    "sa=bpy.data.objects.get('AppleStem')\n"
    "if sa: sa.location=(-0.082, -0.06, -0.058)\n"  # stem above apple top
    "result={'ok':True}\n",
    timeout=10
)
print("Apple fix:", r)

# Verify apple world position
r = blender(
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a:\n"
    "    vs=[a.matrix_world @ v.co for v in a.data.vertices]\n"
    "    result={'loc_z':round(a.location.z,3), 'world_zmax':round(max(v.z for v in vs),3), 'world_zmin':round(min(v.z for v in vs),3)}\n"
    "else: result={'err':'no apple'}\n",
    timeout=10
)
print("Apple world z:", r)

render_save("D:/blender-claude/renders/basket_FINAL.png")
