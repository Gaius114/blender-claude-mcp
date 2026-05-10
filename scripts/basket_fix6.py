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

# Debug: print actual vertex max z for apple in world space
r = blender(
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a:\n"
    "    vs=[a.matrix_world @ v.co for v in a.data.vertices]\n"
    "    result={'apple_loc':list(a.location), 'apple_zmax':round(max(v.z for v in vs),4), 'apple_zmin':round(min(v.z for v in vs),4)}\n"
    "else:\n"
    "    result={'err':'no apple'}\n",
    timeout=10
)
print("Apple debug:", r)

# Reposition apple LOW inside basket (z=0.07 center = well inside)
r = blender(
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a: a.location=(0.06, -0.07, 0.07)\n"
    "sa=bpy.data.objects.get('AppleStem')\n"
    "if sa: sa.location=(0.058, -0.07, 0.138)\n"
    "result={'ok':True}\n",
    timeout=10
)
print("Apple moved:", r)

# Verify
r = blender(
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a:\n"
    "    vs=[a.matrix_world @ v.co for v in a.data.vertices]\n"
    "    result={'apple_loc':list(a.location), 'apple_zmax':round(max(v.z for v in vs),4)}\n"
    "else:\n"
    "    result={'err':'no apple'}\n",
    timeout=10
)
print("Apple after:", r)

render_save("D:/blender-claude/renders/basket_v7.png")
