import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())
    if "error" in r: print("  ERR:", r["error"][:800]); return None
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

# ── 1. CAMERA MUCH FURTHER BACK ────────────────────────────────
for obj in bpy.data.objects:
    if obj.type == 'CAMERA': bpy.data.objects.remove(obj, do_unlink=True)
for obj in bpy.data.objects:
    if "CamTarget" in obj.name: bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.object.camera_add(location=(0.65, -0.95, 0.68))
cam = bpy.context.active_object; cam.name = "Camera"
cam.data.lens = 60
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 1.18
cam.data.dof.aperture_fstop = 8.0
bpy.context.scene.camera = cam

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.02, 0.24))
tgt = bpy.context.active_object; tgt.name = "CamTarget"
tt = cam.constraints.new('TRACK_TO')
tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'

# ── 2. FIX BASKET MATERIAL (proper brown wicker) ───────────────
mat_wicker = bpy.data.materials.get("Wicker")
if mat_wicker:
    t = mat_wicker.node_tree; t.nodes.clear()
    out   = t.nodes.new('ShaderNodeOutputMaterial')
    bsdf  = t.nodes.new('ShaderNodeBsdfPrincipled')
    coord = t.nodes.new('ShaderNodeTexCoord')
    # Horizontal weave bands
    wH = t.nodes.new('ShaderNodeTexWave')
    wH.wave_type = 'BANDS'; wH.bands_direction = 'Z'
    wH.inputs['Scale'].default_value = 32.0
    wH.inputs['Distortion'].default_value = 0.8
    wH.inputs['Detail'].default_value = 2.0
    # Vertical weave bands
    wV = t.nodes.new('ShaderNodeTexWave')
    wV.wave_type = 'BANDS'; wV.bands_direction = 'X'
    wV.inputs['Scale'].default_value = 32.0
    wV.inputs['Distortion'].default_value = 0.8
    wV.inputs['Detail'].default_value = 2.0
    # Combine weaves for color variation
    crH = t.nodes.new('ShaderNodeValToRGB')
    crH.color_ramp.elements[0].color = (0.52, 0.30, 0.10, 1.0)  # dark wicker
    crH.color_ramp.elements[1].color = (0.72, 0.48, 0.20, 1.0)  # light wicker
    # Bump from vertical weave
    bmp = t.nodes.new('ShaderNodeBump')
    bmp.inputs['Strength'].default_value = 1.5
    bmp.inputs['Distance'].default_value = 0.004
    # Mix wave patterns for final color
    mix = t.nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'; mix.inputs['Fac'].default_value = 1.0
    # links
    t.links.new(coord.outputs['Generated'], wH.inputs['Vector'])
    t.links.new(coord.outputs['Generated'], wV.inputs['Vector'])
    t.links.new(wH.outputs['Fac'], crH.inputs['Fac'])
    t.links.new(wV.outputs['Fac'], bmp.inputs['Height'])
    t.links.new(crH.outputs['Color'], mix.inputs[1])
    mix.inputs[2].default_value = (0.85, 0.65, 0.35, 1.0)  # warm highlight
    t.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
    t.links.new(bmp.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Roughness'].default_value = 0.85
    t.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    # Apply to all wicker objects
    for obj in bpy.data.objects:
        if obj.name in ['Basket','Rim','Handle'] or obj.name.startswith('Handle'):
            obj.data.materials.clear()
            obj.data.materials.append(mat_wicker)

# ── 3. REPOSITION FRUITS — lower, more inside basket ──────────
positions = {
    "Apple":     (-0.062,  0.055, 0.255),
    "AppleStem": (-0.065,  0.055, 0.320),
    "Pear":      ( 0.075, -0.040, 0.210),
    "PearStem":  ( 0.078, -0.040, 0.385),
    "Banana":    (-0.040, -0.098, 0.205),
}
for name, (x,y,z) in positions.items():
    obj = bpy.data.objects.get(name)
    if obj: obj.location = (x, y, z)

# Pineapple stays in back, just lower
pine = bpy.data.objects.get("Pineapple")
if pine: pine.location.z = 0.188
for obj in bpy.data.objects:
    if obj.name.startswith("PineLeaf"):
        obj.location.z -= 0.007

# ── 4. WORLD: darker, warmer background ────────────────────────
world = bpy.context.scene.world; world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.72, 0.68, 0.62, 1.0)
    bg.inputs["Strength"].default_value = 0.35

result = {"ok": True}
""", timeout=15)
print("Fix2:", r)

render_save("D:/blender-claude/renders/basket_v3.png", w=1280, h=720, exposure=0.10)
