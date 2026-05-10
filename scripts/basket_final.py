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

# Move apple up so it peeks above basket rim
r = blender(
    "import bpy\n"
    "a=bpy.data.objects.get('Apple')\n"
    "if a: a.location=(-0.10, 0.00, 0.138)\n"
    "sa=bpy.data.objects.get('AppleStem')\n"
    "if sa: sa.location=(-0.103, 0.00, 0.202)\n"
    "b=bpy.data.objects.get('Banana')\n"
    "if b: b.location=(0.0, 0.0, -0.080)\n"
    "result={'ok':True}\n",
    timeout=10
)
print("Fruits:", r)

# Replace camera with better angle
r = blender(
    "import bpy\n"
    "to_del=[o for o in bpy.data.objects if o.type=='CAMERA']\n"
    "for o in to_del: bpy.data.objects.remove(o, do_unlink=True)\n"
    "to_del2=[o for o in bpy.data.objects if 'Target' in o.name and o.type=='EMPTY']\n"
    "for o in to_del2: bpy.data.objects.remove(o, do_unlink=True)\n"
    "bpy.ops.object.camera_add(location=(0.48,-0.80,0.78))\n"
    "cam=bpy.context.active_object\n"
    "cam.name='Camera'\n"
    "cam.data.lens=62\n"
    "cam.data.dof.use_dof=True\n"
    "cam.data.dof.focus_distance=1.0\n"
    "cam.data.dof.aperture_fstop=7.1\n"
    "bpy.context.scene.camera=cam\n"
    "bpy.ops.object.empty_add(type='PLAIN_AXES',location=(0.01,0.00,0.21))\n"
    "tgt=bpy.context.active_object\n"
    "tgt.name='CamTarget'\n"
    "tt=cam.constraints.new('TRACK_TO')\n"
    "tt.target=tgt\n"
    "tt.track_axis='TRACK_NEGATIVE_Z'\n"
    "tt.up_axis='UP_Y'\n"
    "result={'ok':True}\n",
    timeout=10
)
print("Camera:", r)

render_save("D:/blender-claude/renders/basket_v5.png", w=1920, h=1080, exposure=0.09)
