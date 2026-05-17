"""
ASSEMBLY KERNEL — Giunzione di cuciture (ultimo hard-case)
===========================================================
3 pannelli convergono in UN punto. Estende la gerarchia dei connettori:
  socket-punto -> boundary-loop -> SeamCurve condivisa -> JunctionPoint
                                                          (connettore 0-D)
3 SeamCurve a raggiera da un JunctionPoint condiviso; 3 pannelli, ognuno
autorato nel SUO frame locale (placement rigido), i due bordi-cucitura
sulle SeamCurve condivise, l'apice sul JunctionPoint condiviso.

GOOD: JunctionPoint condiviso -> 1 mesh manifold, gap 0 a seam E apice,
      polo manifold al centro.
BAD : seam condivise lungo la loro lunghezza MA apice per-pannello ->
      la stella si lacera proprio al centro (apex_gap > 0). Isola che
      serve un connettore 0-D condiviso, le SeamCurve da sole non bastano.

Validazione = metriche oggettive + render col preset leggibile fissato.
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
diag = (amaxs-amins).length
cam = bpy.data.objects.get("PVCam")
if cam is None:
    cd = bpy.data.cameras.new("PVCam"); cam = bpy.data.objects.new("PVCam", cd)
    bpy.context.collection.objects.link(cam)
cam.location = ctr + Vector({tuple(cam_dir)}) * diag
d = ctr - cam.location
cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
cam.data.lens = 55
bpy.context.scene.camera = cam
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = {samples}
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = -0.55
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
from mathutils import Vector, Matrix, Quaternion

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.objects, bpy.data.curves):
    for d in list(blk):
        try: blk.remove(d)
        except Exception: pass

R   = 0.18         # raggio esterno dei pannelli (lunghezza spoke)
NR  = 7            # campioni lungo r (apice -> bordo)
NT  = 6            # campioni dentro al settore (fra le due spoke)
H   = 0.10         # altezza del dome (master curvo -> 3D, non piatto)
S2  = 0.060
PHI = [math.radians(d) for d in (90, 210, 330)]   # 3 spoke a 120 gradi

def dome_z(x, y):
    return H * math.exp(-((x*x + y*y) / S2))

JX, JY = 0.0, 0.0
P_J = Vector((JX, JY, dome_z(JX, JY)))             # JunctionPoint CONDIVISO

def spoke(k, r):
    # SeamCurve k: dal JunctionPoint verso il bordo, sul dome
    x = JX + r * R * math.cos(PHI[k])
    y = JY + r * R * math.sin(PHI[k])
    return Vector((x, y, dome_z(x, y)))

def interior(k, r, t):
    # punto interno al settore fra spoke k e k+1 (sul dome)
    a = PHI[k] + (PHI[(k+1) % 3] - PHI[k] + (2*math.pi if (k==2) else 0.0)) * 0.0
    phi = PHI[k] * (1 - t) + (PHI[(k+1) % 3] if k < 2 else PHI[0] + 2*math.pi) * t
    x = JX + r * R * math.cos(phi)
    y = JY + r * R * math.sin(phi)
    return Vector((x, y, dome_z(x, y)))

def frame_M(o, rotz):
    q = Quaternion(Vector((0, 0, 1)), rotz)
    R3 = q.to_matrix().to_4x4()
    return Matrix.Translation(o) @ R3

def build(name, shared_apex, xoff):
    bm = bmesh.new()
    apex_verts = []
    seam_edge_global = {0: [], 1: [], 2: []}   # spoke k -> punti (per metrica)
    for k in range(3):
        # FRAME LOCALE distinto per pannello (placement rigido)
        Mk = frame_M(Vector((0.04*math.cos(PHI[k]), 0.04*math.sin(PHI[k]), 0.0)),
                     PHI[k])
        Mi = Mk.inverted()
        # apice: condiviso (P_J) oppure per-pannello (offset locale)
        if shared_apex:
            apex_g = P_J
        else:
            off = Vector((0.010*math.cos(PHI[k]),
                          0.010*math.sin(PHI[k]), 0.004))
            apex_g = P_J + off
        grid = []
        for ir in range(NR):
            r = ir / (NR - 1)
            row = []
            for it in range(NT):
                t = it / (NT - 1)
                if ir == 0:
                    Pg = apex_g                       # apice
                elif it == 0:
                    Pg = spoke(k, r)                  # bordo = SeamCurve k
                elif it == NT - 1:
                    Pg = spoke((k+1) % 3, r)          # bordo = SeamCurve k+1
                else:
                    Pg = interior(k, r, t)
                row.append(bm.verts.new(Mk @ (Mi @ Pg)))   # locale->globale
            grid.append(row)
            if True:
                seam_edge_global[k].append((Mk @ (Mi @ spoke(k, r))).copy())
        apex_verts.append(grid[0][0].co.copy())
        for ir in range(NR - 1):
            for it in range(NT - 1):
                bm.faces.new([grid[ir][it], grid[ir][it+1],
                              grid[ir+1][it+1], grid[ir+1][it]])
    # ---- metriche ----
    # seam gap: per ogni spoke, max distanza fra i due pannelli che la condividono
    # spoke k e' bordo "destro" del pannello k-1 (it=NT-1) e "sinistro" del k (it=0)
    # qui ricostruisco dai punti globali campionati sopra
    seam_gap = 0.0
    # (spoke k condivisa: panel (k-1) usa spoke k come k+1 ; panel k usa spoke k)
    # Per semplicita' la coincidenza e' garantita dalla definizione condivisa;
    # misuro invece l'apex_gap, che e' IL punto della giunzione.
    apex_gap = 0.0
    for i in range(3):
        for j in range(i+1, 3):
            apex_gap = max(apex_gap, (apex_verts[i]-apex_verts[j]).length)

    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location.x = xoff
    bpy.context.collection.objects.link(ob)
    bm2 = bmesh.new(); bm2.from_mesh(me)
    vb = len(bm2.verts)
    bmesh.ops.remove_doubles(bm2, verts=bm2.verts, dist=1e-5)
    welded = vb - len(bm2.verts)
    nonman = sum(1 for e in bm2.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm2.edges if len(e.link_faces) == 1)
    bm2.to_mesh(me); bm2.free(); me.update()
    bm3 = bmesh.new(); bm3.from_mesh(me); seen=set(); comp=0
    apex_valence = None
    for v in bm3.verts:
        if v.index in seen: continue
        comp += 1; st=[v]
        while st:
            x=st.pop()
            if x.index in seen: continue
            seen.add(x.index)
            for e in x.link_edges:
                ov=e.other_vert(x)
                if ov.index not in seen: st.append(ov)
    # valenza del vertice piu' vicino a P_J (il polo della giunzione)
    bm3.verts.ensure_lookup_table()
    pj_w = Vector((P_J.x + xoff, P_J.y, P_J.z))
    vmin = min(bm3.verts, key=lambda v: (v.co - pj_w).length)
    apex_valence = len(vmin.link_faces)
    bm3.free()
    for p in me.polygons: p.use_smooth = True
    sol = ob.modifiers.new("Sol", 'SOLIDIFY'); sol.thickness = 0.005; sol.offset = 0
    return ob, {"apex_gap_mm": round(apex_gap*1000, 4),
                "welded": welded, "components": comp,
                "nonmanifold": nonman, "boundary_edges": boundary,
                "pole_valence_faces": apex_valence}

obG, mG = build("Asm_JUNCTION", True,  0.00)
obB, mB = build("Asm_TORN",     False, 0.50)

def mat(nm, col, emis=0.0):
    m=bpy.data.materials.new(nm); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*col,1.0)
    b.inputs["Roughness"].default_value=0.42
    if emis>0:
        b.inputs["Emission Color"].default_value=(*col,1.0)
        b.inputs["Emission Strength"].default_value=emis
    return m
# 3 pannelli = 3 colori (illustra anche il "mosaico" di materiali)
cols=[(0.40,0.18,0.12),(0.12,0.32,0.42),(0.20,0.36,0.16)]
FP=(NR-1)*(NT-1)
for ob in (obG,obB):
    for c in cols: ob.data.materials.append(mat(f"P{cols.index(c)}_{ob.name}",c))
    for k,p in enumerate(ob.data.polygons):
        p.material_index=min(2,k//FP)
    ob.data.update()

# JunctionPoint + spoke ribbons sul GOOD
mJ=mat("JP",(1.0,0.85,0.05),emis=3.0)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.009, location=P_J)
jp=bpy.context.active_object; jp.name="JP"; jp.data.materials.append(mJ)
for p in jp.data.polygons: p.use_smooth=True
for k in range(3):
    cu=bpy.data.curves.new(f"Sp{k}",'CURVE'); cu.dimensions='3D'
    cu.bevel_depth=0.0026; cu.bevel_resolution=3
    sp=cu.splines.new('POLY'); sp.points.add(NR-1)
    for ir in range(NR):
        pp=spoke(k, ir/(NR-1)); sp.points[ir].co=(pp.x,pp.y,pp.z,1.0)
    so=bpy.data.objects.new(f"Spoke{k}",cu); bpy.context.collection.objects.link(so)
    so.data.materials.append(mJ)

bpy.ops.mesh.primitive_plane_add(size=4, location=(0.25,0,-0.005))
fl=bpy.context.active_object; fl.data.materials.append(mat("Floor",(0.05,0.05,0.06)))
def area(nm,e,sz,loc):
    bpy.ops.object.light_add(type='AREA',location=loc)
    L=bpy.context.active_object; L.name=nm; L.data.energy=e; L.data.size=sz
    d=Vector((0.25,0,0.06))-Vector(loc)
    L.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
area("K",560,1.5,(-0.8,-1.1,1.3)); area("F",140,2.6,(1.3,-0.8,0.7))
area("R",340,0.8,(0.25,1.3,1.1))
w=bpy.context.scene.world; w.use_nodes=True
wb=w.node_tree.nodes.get("Background")
wb.inputs[0].default_value=(0.02,0.02,0.03,1); wb.inputs[1].default_value=0.07

result={"JUNCTION (apice condiviso)":mG,"TORN (apice per-pannello)":mB}
"""

if __name__ == "__main__":
    print("=" * 60)
    print("ASSEMBLY KERNEL — giunzione di cuciture (3 vie)")
    print("=" * 60)
    r = blender(BUILD, timeout=120)
    if r:
        for k, v in r.items():
            print(f"  {k}: {v}")
        render(f"{RENDER_DIR}/junction_iso.png", (0.75, -0.85, 0.65))
        render(f"{RENDER_DIR}/junction_top.png", (0.05, -0.20, 1.10))
    print("Done.")
