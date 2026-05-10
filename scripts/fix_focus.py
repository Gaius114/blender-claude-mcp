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

def render_save(path, w=1280, h=720, exposure=0.1):
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
from mathutils import Vector

cam = bpy.data.objects.get("Camera")
if not cam:
    result = {"error": "no camera"}
else:
    # ── Calcola distanza esatta dalla camera al centro del donut ──────────────
    # Il centro ottico del donut: (0, 0, 0.03) — top della glassa
    cam_loc    = cam.matrix_world.translation
    focus_point = Vector((0.0, 0.0, 0.035))
    exact_dist  = (focus_point - cam_loc).length

    # ── Imposta focus sulla distanza reale ────────────────────────────────────
    cam.data.dof.use_dof           = True
    cam.data.dof.focus_distance    = exact_dist
    cam.data.dof.aperture_fstop   = 4.0   # f/4: sfocato lo sfondo, nitido il sogg.

    # ── Alza leggermente la camera per vedere la glassa + sprinkles ──────────
    # Mantieni la stessa distanza orizzontale, alza di 3cm
    cam.location.z += 0.035
    cam.location.y -= 0.04   # un po' piu lontana

    # Ricalcola distanza focus con nuova posizione
    cam_loc    = cam.matrix_world.translation
    exact_dist = (focus_point - cam_loc).length
    cam.data.dof.focus_distance = exact_dist

    # ── Icing: aumenta saturazione del rosa ───────────────────────────────────
    mat_icing = bpy.data.materials.get("Icing")
    if mat_icing:
        for n in mat_icing.node_tree.nodes:
            if n.bl_idname == "ShaderNodeValToRGB":
                n.color_ramp.elements[0].color = (0.98, 0.48, 0.58, 1.0)
                n.color_ramp.elements[1].color = (0.92, 0.35, 0.48, 1.0)
                break

    # ── Sprinkles: colori piu saturi e vivaci ─────────────────────────────────
    color_updates = {
        "Spr_Red":    (0.90, 0.05, 0.05),
        "Spr_Blue":   (0.05, 0.15, 0.90),
        "Spr_Yellow": (0.98, 0.88, 0.02),
        "Spr_Green":  (0.05, 0.72, 0.15),
        "Spr_Purple": (0.55, 0.05, 0.85),
        "Spr_Orange": (0.98, 0.42, 0.02),
        "Spr_Pink":   (0.98, 0.40, 0.65),
    }
    for mname, col in color_updates.items():
        mat = bpy.data.materials.get(mname)
        if mat:
            for n in mat.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    n.inputs["Base Color"].default_value = (*col, 1.0)
                    n.inputs["Roughness"].default_value  = 0.25
                    break

    # ── Key light: illumina la glassa dall'alto ───────────────────────────────
    key = bpy.data.objects.get("Key")
    if key:
        key.location    = (-0.28, -0.22, 0.50)
        key.data.energy = 28
        key.data.size   = 0.55
        key.rotation_euler = (math.radians(40), 0, math.radians(-45))

    result = {
        "focus_distance": round(exact_dist, 4),
        "cam_z": round(cam.location.z, 4),
        "fstop": cam.data.dof.aperture_fstop,
    }
""", timeout=10)
print("Focus:", r)

render_save("D:/blender-claude/renders/donut_focus.png", w=1920, h=1080, exposure=0.08)
