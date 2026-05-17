"""
ASSEMBLY KERNEL — Composizione di cuciture (validazione)
=========================================================
3 pannelli (quarter, vamp, toe-cap) su un last globale, autorati in frame
LOCALI DIVERSI, uniti da 2 SeamCurve condivise. Il VAMP partecipa a
ENTRAMBE le cuciture -> test della *composizione* (un pezzo su piu' seam).

Claim: con tutte le seam condivise -> 1 sola mesh connessa, gap 0, manifold.
Controllo negativo: se UNA seam non e' condivisa, la catena si rompe SOLO
li' (toe-cap staccato) -> componenti = 2. Dimostra che la disciplina deve
valere per OGNI cucitura.

Validazione = metriche per-seam (gap, weld, componenti, manifold) +
render leggibile (spessore solidify + seam evidenziate + framing corretto).
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
        print("ERR:", r["error"][:1600])
        return None
    return r.get("ok")


def render(path, cam_dir, w=1280, h=820, samples=64):
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
diag = (amaxs-amins).length
cam = bpy.data.objects.get("PVCam")
if cam is None:
    cd = bpy.data.cameras.new("PVCam"); cam = bpy.data.objects.new("PVCam", cd)
    bpy.context.collection.objects.link(cam)
cam.location = ctr + Vector({tuple(cam_dir)}) * diag
d = ctr - cam.location
cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
cam.data.lens = 58
bpy.context.scene.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = {samples}
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = -0.15
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


BUILD = r"""
import bpy, bmesh, math
from mathutils import Vector, Matrix

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.objects, bpy.data.curves):
    for d in list(blk):
        try: blk.remove(d)
        except Exception: pass

STATIONS = [
    (0.000, 0.034, 0.030, 0.085),
    (0.080, 0.045, 0.020, 0.095),
    (0.160, 0.052, 0.017, 0.075),
    (0.220, 0.046, 0.020, 0.055),
    (0.270, 0.020, 0.030, 0.043),
]
NS = len(STATIONS); E = 2.4
def lerp(a, b, s): return a + (b - a) * s

def last_S(t, a):
    f = max(0.0, min(0.999999, t)) * (NS - 1)
    i = int(f); s = f - i
    x0,w0,b0,p0 = STATIONS[i]
    x1,w1,b1,p1 = STATIONS[min(i+1, NS-1)]
    x=lerp(x0,x1,s); hw=lerp(w0,w1,s); zb=lerp(b0,b1,s); zt=lerp(p0,p1,s)
    cz=(zb+zt)*0.5; hz=(zt-zb)*0.5
    ca=math.cos(a); sa=math.sin(a)
    y=math.copysign(abs(ca)**(2.0/E), ca)*hw
    z=cz+math.copysign(abs(sa)**(2.0/E), sa)*hz
    return Vector((x,y,z))

def surface_frame(t, a):
    o  = last_S(t, a)
    dt = (last_S(t+1e-4,a)-last_S(t-1e-4,a)).normalized()
    da = (last_S(t,a+1e-4)-last_S(t,a-1e-4)).normalized()
    n  = dt.cross(da).normalized()
    da = n.cross(dt).normalized()
    R = Matrix((dt, da, n)).transposed().to_4x4()
    return Matrix.Translation(o) @ R

A_LO = math.pi/2 - 1.15
A_HI = math.pi/2 + 1.15
T_A  = 0.42          # cucitura quarter|vamp
T_B  = 0.78          # cucitura vamp|toecap
NA   = 16
NT   = 8

# ── SeamCurve: due curve UNICHE possedute dall'assieme (in globale) ──────────
def seam_curve(cid, j):
    a = lerp(A_LO, A_HI, j/(NA-1))
    return last_S(T_A if cid == 'A' else T_B, a)

def build_panel(bm, M, t0, t1, edge0, edge1):
    # edge*: ('shared', cid) -> usa SeamCurve condivisa
    #        ('own', cid)    -> autora il bordo nel proprio locale (no share)
    #        ('free', None)  -> bordo libero (interpola il last, nessun vincolo)
    Mi = M.inverted()
    grid = []; seam_rows = {}
    for i in range(NT):
        t = lerp(t0, t1, i/(NT-1))
        edge = edge0 if i == 0 else (edge1 if i == NT-1 else ('free', None))
        row = []
        for j in range(NA):
            mode, cid = edge
            if mode == 'shared':
                Pg = seam_curve(cid, j)
            elif mode == 'own':
                a = lerp(A_LO+0.13, A_HI+0.13, j/(NA-1))   # bordo "egoista"
                Pg = last_S(T_A if cid=='A' else T_B, a)
            else:
                a = lerp(A_LO, A_HI, j/(NA-1))
                Pg = last_S(t, a)
            row.append(bm.verts.new(M @ (Mi @ Pg)))   # locale -> globale
        grid.append(row)
        if edge[0] in ('shared','own'):
            seam_rows[edge[1]] = [v.co.copy() for v in row]
    bm.verts.ensure_lookup_table()
    for i in range(NT-1):
        for j in range(NA-1):
            bm.faces.new([grid[i][j], grid[i][j+1],
                          grid[i+1][j+1], grid[i+1][j]])
    return seam_rows

def components(me):
    bm = bmesh.new(); bm.from_mesh(me)
    seen=set(); n=0
    for v in bm.verts:
        if v.index in seen: continue
        n+=1; st=[v]
        while st:
            x=st.pop()
            if x.index in seen: continue
            seen.add(x.index)
            for e in x.link_edges:
                ov=e.other_vert(x)
                if ov.index not in seen: st.append(ov)
    bm.free(); return n

def make(name, shareB, xoff):
    bm = bmesh.new()
    # FRAME LOCALI DIVERSI per i 3 pannelli
    Mq = surface_frame(0.15, math.pi/2)
    Mv = surface_frame(0.55, math.pi/2)
    Mt = surface_frame(0.90, math.pi/2)
    sq = build_panel(bm, Mq, 0.00, T_A, ('free',None),   ('shared','A'))
    sv = build_panel(bm, Mv, T_A,  T_B, ('shared','A'),   ('shared','B'))
    eB = ('shared','B') if shareB else ('own','B')
    st = build_panel(bm, Mt, T_B,  1.00, eB,              ('free',None))
    gapA = max((sq['A'][j]-sv['A'][j]).length for j in range(NA))
    gapB = max((sv['B'][j]-st['B'][j]).length for j in range(NA))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location.x = xoff
    bpy.context.collection.objects.link(ob)
    bm2 = bmesh.new(); bm2.from_mesh(me)
    vb = len(bm2.verts)
    bmesh.ops.remove_doubles(bm2, verts=bm2.verts, dist=1e-5)
    welded = vb - len(bm2.verts)
    nonman = sum(1 for e in bm2.edges if len(e.link_faces) > 2)
    bm2.to_mesh(me); bm2.free(); me.update()
    comp = components(me)
    for p in me.polygons: p.use_smooth = True
    # spessore -> leggibile come pelle, non lamina
    sol = ob.modifiers.new("Sol", 'SOLIDIFY')
    sol.thickness = 0.005; sol.offset = 0.0
    return ob, {"seamA_gap_mm": round(gapA*1000,3),
                "seamB_gap_mm": round(gapB*1000,3),
                "welded": welded, "expected_full": 2*NA,
                "components": comp, "nonmanifold": nonman}

obG, mG = make("Asm_COMPOSED", True,  0.00)   # tutte le seam condivise
obB, mB = make("Asm_BROKEN",   False, 0.42)   # seam B non condivisa

# materiali: 3 tinte (quarter/vamp/toecap) -> seam visibili come bordi colore
def mat(nm,col,rough=0.5):
    m=bpy.data.materials.new(nm); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*col,1.0)
    b.inputs["Roughness"].default_value=rough
    return m
mQ=mat("Quarter",(0.15,0.27,0.36)); mV=mat("Vamp",(0.36,0.22,0.14))
mT=mat("ToeCap",(0.30,0.34,0.16))
FPR=(NT-1)*(NA-1)   # facce per pannello
for ob in (obG,obB):
    ob.data.materials.append(mQ); ob.data.materials.append(mV)
    ob.data.materials.append(mT)
    for k,p in enumerate(ob.data.polygons):
        p.material_index = 0 if k<FPR else (1 if k<2*FPR else 2)
    ob.data.update()

# SEAM-RIBBON: disegna le 2 curve condivise come tubi gialli sul GOOD
mS=bpy.data.materials.new("SeamMark"); mS.use_nodes=True
bs=mS.node_tree.nodes.get("Principled BSDF")
bs.inputs["Base Color"].default_value=(1.0,0.85,0.05,1.0)
bs.inputs["Emission Color"].default_value=(1.0,0.7,0.0,1.0)
bs.inputs["Emission Strength"].default_value=2.0
for cid in ('A','B'):
    cu=bpy.data.curves.new(f"Seam{cid}",'CURVE'); cu.dimensions='3D'
    cu.bevel_depth=0.0028; cu.bevel_resolution=3
    sp=cu.splines.new('POLY'); sp.points.add(NA-1)
    for j in range(NA):
        p=seam_curve(cid,j); sp.points[j].co=(p.x,p.y,p.z,1.0)
    so=bpy.data.objects.new(f"SeamMark_{cid}",cu)
    bpy.context.collection.objects.link(so)
    so.data.materials.append(mS)

bpy.ops.mesh.primitive_plane_add(size=6, location=(0.2,0,-0.04))
fl=bpy.context.active_object; fl.data.materials.append(mat("Floor",(0.05,0.05,0.06)))
def area(nm,e,sz,loc):
    bpy.ops.object.light_add(type='AREA',location=loc)
    L=bpy.context.active_object; L.name=nm; L.data.energy=e; L.data.size=sz
    d=Vector((0.2,0,0.05))-Vector(loc)
    L.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
area("K",1400,2.5,(-1.6,-2.2,2.2)); area("F",350,4,(2.2,-1.5,1.2))
area("R",900,1.2,(0.2,2.4,2.0))
w=bpy.context.scene.world; w.use_nodes=True
wb=w.node_tree.nodes.get("Background")
wb.inputs[0].default_value=(0.02,0.02,0.03,1); wb.inputs[1].default_value=0.08

result={"COMPOSED (tutte condivise)":mG,"BROKEN (seam B no-share)":mB}
"""

if __name__ == "__main__":
    print("=" * 60)
    print("ASSEMBLY KERNEL — composizione: 3 pannelli, 2 cuciture")
    print("=" * 60)
    r = blender(BUILD, timeout=120)
    if r:
        for k, v in r.items():
            print(f"  {k}: {v}")
        render(f"{RENDER_DIR}/compose_top.png",  (0.30, -0.55, 0.80))
        render(f"{RENDER_DIR}/compose_iso.png",  (0.85, -0.85, 0.45))
    print("Done.")
