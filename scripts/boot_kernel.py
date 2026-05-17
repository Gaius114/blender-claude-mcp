"""
STIVALE via assembly_kernel — validazione end-to-end della skill aggiornata
============================================================================
Applica il kernel ESATTAMENTE come prescrive la sezione "PARADIGMA PANNELLI
/ CUCITURE" di blender-arch:
  - base globale = un "last" (forma del piede) come master surface
  - cuciture REALI del bootmaking come connettori CONDIVISI (SeamCurve)
  - pannelli (quarter, vamp, toe-cap) via panel_on_master, bordi VINCOLATI
  - finalize(weld) -> 1 mesh ; validate() come GATE ; studio_setup() preset

Chiude ad anello il fallimento "calzino": l'upper non e' piu' un loft-blob
ma pannelli su un last cuciti via connettori condivisi.
Scala: metri. Engine: BLENDER_EEVEE (Blender 5.1).
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


BUILD = r"""
import sys, importlib, math
KP = r"D:\blender-claude\kernel"
if KP not in sys.path: sys.path.insert(0, KP)
import assembly_kernel as ak
importlib.reload(ak)
import bpy
from mathutils import Vector

ak._clear()

# ── BASE GLOBALE: il "last" (forma del piede) come master surface ───────────
STATIONS = [
    (0.000, 0.034, 0.030, 0.085),   # tallone
    (0.080, 0.045, 0.020, 0.095),   # collo del piede
    (0.160, 0.052, 0.017, 0.075),   # avampiede
    (0.220, 0.046, 0.020, 0.055),   # toe box
    (0.270, 0.020, 0.030, 0.043),   # punta
]
NS = len(STATIONS); E = 2.4
def lerp(a,b,s): return a + (b-a)*s
def last(t, a):
    f = max(0.0, min(0.999999, t)) * (NS-1)
    i = int(f); s = f - i
    x0,w0,b0,p0 = STATIONS[i]
    x1,w1,b1,p1 = STATIONS[min(i+1,NS-1)]
    x=lerp(x0,x1,s); hw=lerp(w0,w1,s); zb=lerp(b0,b1,s); zt=lerp(p0,p1,s)
    cz=(zb+zt)*0.5; hz=(zt-zb)*0.5
    ca=math.cos(a); sa=math.sin(a)
    y=math.copysign(abs(ca)**(2.0/E), ca)*hw
    z=cz+math.copysign(abs(sa)**(2.0/E), sa)*hz
    return Vector((x,y,z))

# banda angolare dell'upper: avvolge il piede lasciando APERTO il fondo
# (la "feather"/linea di montaggio = bordo aperto atteso, non un difetto)
GAP = 0.42                     # mezza apertura inferiore (rad)
A0  = -math.pi/2 + GAP         # da poco sopra il fondo, lato +
A1  =  3*math.pi/2 - GAP       # ... sopra la punta ... fino al fondo lato -
NR  = 28                       # campioni attorno al piede (lungo la cucitura)
def band(j): return A0 + (A1 - A0) * (j/(NR-1))

# ── CUCITURE REALI come connettori CONDIVISI (SeamCurve) ────────────────────
T_VQ = 0.42                    # cucitura vamp | quarter
T_TC = 0.74                    # cucitura toe-cap | vamp
A = ak.Assembly("StivaleKernel")
seam_vq = A.seam("vamp_quarter", [last(T_VQ, band(j)) for j in range(NR)])
seam_tc = A.seam("toecap_vamp",  [last(T_TC, band(j)) for j in range(NR)])

# ── PANNELLI: panel_on_master, bordi VINCOLATI ai connettori condivisi ───────
# Convenzione kernel: master(r,t); r-> attorno al piede (NR), t-> longitudinale.
# edge_t0/edge_t1 legano le colonne it=0 / it=NT-1 (curve di lunghezza NR).
NT = 7
def mk_master(tA, tB):
    def m(r, t):
        # r in [0,1] -> indice attorno ; t in [0,1] -> da tA a tB (longitud.)
        return last(lerp(tA, tB, t), band(round(r*(NR-1))))
    return m

# quarter: tallone -> seam_vq    (edge_t1 = seam_vq)
A.panel_on_master(mk_master(0.0, T_VQ), NR, NT,
                  edge_t1=seam_vq, material=(0.052,0.030,0.014))
# vamp: seam_vq -> seam_tc       (su ENTRAMBE le cuciture = composizione)
A.panel_on_master(mk_master(T_VQ, T_TC), NR, NT,
                  edge_t0=seam_vq, edge_t1=seam_tc,
                  material=(0.060,0.034,0.016))
# toe-cap: seam_tc -> punta      (edge_t0 = seam_tc ; punta = bordo libero)
A.panel_on_master(mk_master(T_TC, 1.0), NR, NT,
                  edge_t0=seam_tc, material=(0.045,0.026,0.012))

A.finalize(weld=True)
m = A.validate()
ak.studio_setup()

# GATE oggettivo (come prescrive la skill)
gate_ok = (m["components"] == 1 and m["nonmanifold"] == 0)
result = {"validate": m, "GATE_PASS": bool(gate_ok),
          "seams": list(A.seams.keys())}
"""


def render(path, cam_dir=(0.85, -0.85, 0.45), w=1280, h=860, samples=64):
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
ctr=(amins+amaxs)*0.5; diag=max((amaxs-amins).length,0.1)
cam=bpy.data.objects.get("PVCam")
if cam is None:
    cd=bpy.data.cameras.new("PVCam"); cam=bpy.data.objects.new("PVCam",cd)
    bpy.context.collection.objects.link(cam)
cam.location=ctr+Vector({tuple(cam_dir)})*diag
d=ctr-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
cam.data.lens=58
bpy.context.scene.camera=cam
sc.render.engine="BLENDER_EEVEE"; sc.eevee.taa_render_samples={samples}
sc.render.resolution_x={w}; sc.render.resolution_y={h}
sc.render.use_compositing=False
import tempfile, base64, os
tmp=tempfile.mktemp(suffix=".png"); sc.render.filepath=tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64=base64.b64encode(f.read()).decode()
os.remove(tmp); result={{"b64":b64}}
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
    print("STIVALE via assembly_kernel — validazione skill aggiornata")
    print("=" * 60)
    r = blender(BUILD, timeout=120)
    if r:
        print("  validate:", r.get("validate"))
        print("  seams   :", r.get("seams"))
        print("  GATE_PASS:", r.get("GATE_PASS"))
        render(f"{RENDER_DIR}/boot_kernel.png")
    print("Done.")
