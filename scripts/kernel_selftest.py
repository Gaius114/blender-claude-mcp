"""
Harness del self-test del kernel formale.
Carica D:/blender-claude/kernel/assembly_kernel.py in Blender, ricostruisce
via la API FORMALE due casi gia' validati (giunzione 3-vie + catena curva),
verifica le metriche (componenti=1, non-manifold=0) e renderizza col preset.
Se PASS_ALL=True -> la formalizzazione preserva il comportamento validato.
"""

import urllib.request, json, base64, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLENDER_URL = "http://localhost:7234"
RENDER_DIR  = "D:/blender-claude/renders"


def blender(code, timeout=120):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 15)
    r    = json.loads(resp.read().decode())
    if "error" in r:
        print("ERR:", r["error"][:1800])
        return None
    return r.get("ok")


BOOTSTRAP = r"""
import sys, importlib
KP = r"D:\blender-claude\kernel"
if KP not in sys.path:
    sys.path.insert(0, KP)
import assembly_kernel as ak
importlib.reload(ak)
result = ak.selftest()
"""


def render(path, cam_dir, w=1280, h=860, samples=64):
    code = f"""
import bpy
from mathutils import Vector
sc = bpy.context.scene
amins = Vector(( 1e9, 1e9, 1e9)); amaxs = Vector((-1e9,-1e9,-1e9))
for o in bpy.data.objects:
    if o.type!='MESH' or not o.name.startswith("Asm_"): continue
    for c in o.bound_box:
        wc = o.matrix_world @ Vector(c)
        amins.x=min(amins.x,wc.x); amins.y=min(amins.y,wc.y); amins.z=min(amins.z,wc.z)
        amaxs.x=max(amaxs.x,wc.x); amaxs.y=max(amaxs.y,wc.y); amaxs.z=max(amaxs.z,wc.z)
ctr = (amins+amaxs)*0.5
diag = max((amaxs-amins).length, 0.1)
cam = bpy.data.objects.get("PVCam")
if cam is None:
    cd = bpy.data.cameras.new("PVCam"); cam = bpy.data.objects.new("PVCam", cd)
    bpy.context.collection.objects.link(cam)
cam.location = ctr + Vector({tuple(cam_dir)}) * diag
d = ctr - cam.location
cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
cam.data.lens = 52
bpy.context.scene.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = {samples}
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.render.use_compositing = False
import tempfile, base64, os
tmp = tempfile.mktemp(suffix=".png"); sc.render.filepath = tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
os.remove(tmp)
result = {{"b64": b64}}
"""
    r = blender(code, timeout=200)
    if r and "b64" in r:
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["b64"]))
        print(f"  render -> {path}")
        return True
    print("  render FALLITO")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("KERNEL FORMALE — self-test di non-regressione")
    print("=" * 60)
    r = blender(BOOTSTRAP, timeout=120)
    if r:
        print("  junction:", r.get("junction"))
        print("  chain   :", r.get("chain"))
        print("  PASS_junction:", r.get("PASS_junction"),
              " PASS_chain:", r.get("PASS_chain"),
              " PASS_ALL:", r.get("PASS_ALL"))
        render(f"{RENDER_DIR}/kernel_selftest.png", (0.80, -0.85, 0.55))
    print("Done.")
