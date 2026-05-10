import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())
    if "error" in r: print("  ERR:", r["error"][:800]); return None
    return r.get("ok")

def render_save(path, w=1280, h=720, exposure=0.10):
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

r = blender("""
import bpy, math

# Basket: h=0.19, interior radius ~0.185
# Rim is at z = 0.19
# All fruits geometry is built with vertices at specific world positions
# Object.location offsets all vertices

# ── APPLE (built at center z=0.285) → want center at z=0.085 ──
apple = bpy.data.objects.get("Apple")
if apple:
    apple.location = (-0.065, 0.060, 0.086)
stem_a = bpy.data.objects.get("AppleStem")
if stem_a:
    stem_a.location = (-0.068, 0.060, 0.152)

# ── PEAR (mesh base at pz_off=0.19) → want base at z=0.02 ─────
# delta = 0.02 - 0.19 = -0.17
pear = bpy.data.objects.get("Pear")
if pear:
    pear.location = (0.0, 0.0, -0.168)   # shifts pear base to z≈0.022
stem_p = bpy.data.objects.get("PearStem")
if stem_p:
    # stem was at (0.09, -0.04, 0.432); move down -0.168
    stem_p.location = (0.09, -0.04, 0.264)

# ── BANANA (arc center bz_c=0.215) → want middle at z=0.128 ───
# delta = 0.128 - 0.215 = -0.087
banana = bpy.data.objects.get("Banana")
if banana:
    banana.location = (0.0, 0.0, -0.087)
    # Banana: arc tips go up by 0.095*(1-cos65°)=0.055 → tips at z=0.183 (below rim 0.19) ✓
    # Banana middle at z=0.128, tips at 0.183

# ── PINEAPPLE (base at oz=0.195) → want base at z=0.015 ──────
# delta = 0.015 - 0.195 = -0.180
pine = bpy.data.objects.get("Pineapple")
if pine:
    pine.location = (0.0, 0.0, -0.180)
    # Pineapple top at 0.015+0.195+0.018=0.228 → peeks 0.038m above rim ✓
for obj in bpy.data.objects:
    if obj.name.startswith("PineLeaf"):
        obj.location.z = -0.180

result = {
    "apple_z": bpy.data.objects.get("Apple").location.z if bpy.data.objects.get("Apple") else None,
    "pear_z": bpy.data.objects.get("Pear").location.z if bpy.data.objects.get("Pear") else None,
    "banana_z": bpy.data.objects.get("Banana").location.z if bpy.data.objects.get("Banana") else None,
}
""", timeout=10)
print("Positions fixed:", r)

render_save("D:/blender-claude/renders/basket_v4.png", w=1280, h=720, exposure=0.10)
