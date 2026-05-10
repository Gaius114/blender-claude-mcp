import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())
    if "error" in r: print("  ERR:", r["error"][:600]); return None
    return r.get("ok")

def render_save(path, w=1280, h=720, exposure=0.12):
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

# ── 1. CAMERA BACK + HIGHER ───────────────────────────────────
cam = bpy.data.objects.get("Camera")
if cam:
    for c in list(cam.constraints): cam.constraints.remove(c)
    cam.location = (0.60, -0.75, 0.62)
    cam.data.lens = 80
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 1.05
    cam.data.dof.aperture_fstop = 7.1

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.22))
    tgt = bpy.context.active_object; tgt.name = "CamTarget2"
    tt = cam.constraints.new('TRACK_TO')
    tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'

# ── 2. FIX HANDLES (assign wicker material) ───────────────────
mat_wicker = bpy.data.materials.get("Wicker")
for obj in bpy.data.objects:
    if obj.name.startswith("Handle"):
        obj.data.materials.clear()
        if mat_wicker:
            obj.data.materials.append(mat_wicker)

# ── 3. FIX PINEAPPLE — replace voronoi with noise bump ────────
mat_pine = bpy.data.materials.get("Pineapple")
if mat_pine:
    t = mat_pine.node_tree; t.nodes.clear()
    out   = t.nodes.new('ShaderNodeOutputMaterial')
    bsdf  = t.nodes.new('ShaderNodeBsdfPrincipled')
    coord = t.nodes.new('ShaderNodeTexCoord')
    ns1   = t.nodes.new('ShaderNodeTexNoise')   # color variation
    ns2   = t.nodes.new('ShaderNodeTexNoise')   # scale pattern
    cr    = t.nodes.new('ShaderNodeValToRGB')
    bmp   = t.nodes.new('ShaderNodeBump')
    # Color: orange-yellow tones
    ns1.inputs['Scale'].default_value = 3.5
    ns1.inputs['Detail'].default_value = 4.0
    cr.color_ramp.elements[0].color = (0.68, 0.38, 0.04, 1.0)
    cr.color_ramp.elements[1].color = (0.90, 0.65, 0.10, 1.0)
    # Diamond pattern for scales
    ns2.inputs['Scale'].default_value = 16.0
    ns2.inputs['Detail'].default_value = 0.0
    ns2.inputs['Roughness'].default_value = 0.0
    bmp.inputs['Strength'].default_value = 1.8
    bmp.inputs['Distance'].default_value = 0.006
    t.links.new(coord.outputs['Generated'], ns1.inputs['Vector'])
    t.links.new(coord.outputs['Generated'], ns2.inputs['Vector'])
    t.links.new(ns1.outputs['Fac'], cr.inputs['Fac'])
    t.links.new(ns2.outputs['Fac'], bmp.inputs['Height'])
    t.links.new(cr.outputs['Color'], bsdf.inputs['Base Color'])
    t.links.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Roughness'].default_value = 0.80
    t.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

# ── 4. SCALE DOWN PEAR ────────────────────────────────────────
pear = bpy.data.objects.get("Pear")
if pear:
    pear.scale = (0.82, 0.82, 0.82)
    bpy.context.view_layer.objects.active = pear
    bpy.ops.object.transform_apply(scale=True)
pear_stem = bpy.data.objects.get("PearStem")
if pear_stem:
    pear_stem.location.z -= 0.040

# ── 5. ADJUST FRUIT POSITIONS more inside basket ──────────────
apple = bpy.data.objects.get("Apple")
if apple:
    apple.location.x = -0.065
    apple.location.y =  0.060
    apple.location.z =  0.270
stem_a = bpy.data.objects.get("AppleStem")
if stem_a:
    stem_a.location = (-0.068, 0.060, 0.338)

banana = bpy.data.objects.get("Banana")
if banana:
    banana.location.z -= 0.010   # slightly lower, sits in basket

# ── 6. KEY LIGHT: more dramatic angle ─────────────────────────
key = bpy.data.objects.get("Key")
if key:
    key.location = (-0.62, -0.68, 1.05)
    key.data.energy = 95

result = {"ok": True}
""", timeout=15)
print("Fixes:", r)

render_save("D:/blender-claude/renders/basket_v2.png", w=1280, h=720, exposure=0.10)
