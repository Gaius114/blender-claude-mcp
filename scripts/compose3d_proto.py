"""
ASSEMBLY KERNEL — Composizione 3D (la tesi)
=============================================
Concatena 3 pezzi curvi (ognuno: spine locale + CAMPO DI FRAME parallel-
transport + sezione) con assi di curvatura DIVERSI, agganciati da 2
SeamCurve condivise. Ogni pezzo autorato nel SUO frame locale, piazzato
con docking rigido sul frame di fine del precedente, bordo iniziale =
SeamCurve condivisa (override -> coincidenza esatta).

Tesi da validare: una forma 3D complessa NON va modellata in un colpo;
EMERGE dalla composizione di pochi pezzi curvi semplici -> 1 sola mesh
manifold, gap 0 a ogni cucitura, geometria genuinamente 3D (non-planare).

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

NA = 10        # campioni larghezza
K  = 12        # passi lungo l'arco di ogni pezzo
RB = 0.12
W  = 0.13
BEND = math.radians(90.0)

def pt_frames(pts):
    n=len(pts); fr=[None]*n
    T0=(pts[1]-pts[0]).normalized()
    up=Vector((0,1,0))
    if abs(T0.dot(up))>0.99: up=Vector((1,0,0))
    Nc=(up-T0*T0.dot(up)).normalized()
    fr[0]=(T0,Nc,T0.cross(Nc).normalized())
    for i in range(1,n):
        Tp,Np,Bp=fr[i-1]
        Tc=(pts[min(i+1,n-1)]-pts[i-1]).normalized() if 0<i<n-1 else (pts[i]-pts[i-1]).normalized()
        ax=Tp.cross(Tc)
        if ax.length>1e-9:
            ax.normalize(); ang=math.acos(max(-1,min(1,Tp.dot(Tc))))
            Ncur=Quaternion(ax,ang)@Np
        else:
            Ncur=Np.copy()
        Ncur=(Ncur-Tc*Tc.dot(Ncur)).normalized()
        Bc=Tc.cross(Ncur).normalized()
        Ncur=Bc.cross(Tc).normalized()
        fr[i]=(Tc,Ncur,Bc)
    return fr

def local_arc(plane):
    pts=[]
    for i in range(K+1):
        a=BEND*i/K
        if plane=='XZ': pts.append(Vector((RB*math.sin(a),0.0,RB*(1-math.cos(a)))))
        else:           pts.append(Vector((RB*math.sin(a),RB*(1-math.cos(a)),0.0)))
    return pts

def frame_M(o,T,N,B):
    return Matrix.Translation(o) @ Matrix((T,N,B)).transposed().to_4x4()

def end_frame(ring_prev, ring_last):
    O=sum(ring_last,Vector())/len(ring_last)
    Op=sum(ring_prev,Vector())/len(ring_prev)
    T=(O-Op).normalized()
    B=(ring_last[-1]-ring_last[0]).normalized()
    N=B.cross(T).normalized()
    B=T.cross(N).normalized()
    return O,T,N,B

bm=bmesh.new()
seam_marks=[]
PLANES=['XZ','XY','XZ']     # assi di curvatura DIVERSI -> path 3D non-planare
all_rings=[]
M_prev=None; prev_two=None

for pi,plane in enumerate(PLANES):
    spine=local_arc(plane)
    FR=pt_frames(spine)                              # CAMPO di frame locale
    # frame locale di partenza (ring0)
    T0,N0,B0=FR[0]
    Mloc0=frame_M(spine[0],T0,N0,B0)
    if pi==0:
        # primo pezzo: placement iniziale arbitrario (base globale)
        Mg0=frame_M(Vector((0,0,0)),Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1)))
        M=Mg0 @ Mloc0.inverted()
    else:
        # DOCKING rigido: frame iniziale -> frame di fine del precedente
        Oe,Te,Ne,Be=prev_end
        Mg=frame_M(Oe,Te,Ne,Be)
        M=Mg @ Mloc0.inverted()
    # costruisci i ring in GLOBALE
    rings=[]
    for idx,(p,(T,N,B)) in enumerate(zip(spine,FR)):
        row=[]
        for j in range(NA):
            y=-W/2 + W*(j/(NA-1))
            row.append(bm.verts.new(M @ (p + B*y)))
        rings.append(row)
    # cucitura condivisa: override ring0 col bordo di fine del pezzo precedente
    if pi>0:
        for j in range(NA):
            rings[0][j].co = prev_last_co[j].copy()
        seam_marks.append([c.copy() for c in prev_last_co])
    bm.verts.ensure_lookup_table()
    for i in range(K):
        for j in range(NA-1):
            bm.faces.new([rings[i][j],rings[i][j+1],
                          rings[i+1][j+1],rings[i+1][j]])
    # prepara dati per il prossimo docking
    prev_last_co=[rings[-1][j].co.copy() for j in range(NA)]
    prev_prev_co=[rings[-2][j].co.copy() for j in range(NA)]
    prev_end=end_frame(prev_prev_co,prev_last_co)
    all_rings.append(rings)

# ── metriche ────────────────────────────────────────────────────────────────
def seam_gap(ringA_last, ringB_first):
    return max((ringA_last[j].co-ringB_first[j].co).length for j in range(NA))
gap1=seam_gap(all_rings[0][-1], all_rings[1][0])
gap2=seam_gap(all_rings[1][-1], all_rings[2][0])

me=bpy.data.meshes.new("Asm_COMPLEX"); bm.to_mesh(me); bm.free()
ob=bpy.data.objects.new("Asm_COMPLEX",me)
bpy.context.collection.objects.link(ob)
bm2=bmesh.new(); bm2.from_mesh(me)
vb=len(bm2.verts)
bmesh.ops.remove_doubles(bm2,verts=bm2.verts,dist=1e-5)
welded=vb-len(bm2.verts)
nonman=sum(1 for e in bm2.edges if len(e.link_faces)>2)
bm2.to_mesh(me); bm2.free(); me.update()
# componenti
bm3=bmesh.new(); bm3.from_mesh(me); seen=set(); comp=0
for v in bm3.verts:
    if v.index in seen: continue
    comp+=1; stq=[v]
    while stq:
        x=stq.pop()
        if x.index in seen: continue
        seen.add(x.index)
        for e in x.link_edges:
            ov=e.other_vert(x)
            if ov.index not in seen: stq.append(ov)
bm3.free()
# bbox -> genuinamente 3D? (tutte e 3 le estensioni non banali)
xs=[v.co.x for v in me.vertices]; ys=[v.co.y for v in me.vertices]; zs=[v.co.z for v in me.vertices]
bbox=(round(max(xs)-min(xs),3),round(max(ys)-min(ys),3),round(max(zs)-min(zs),3))
for p in me.polygons: p.use_smooth=True
sol=ob.modifiers.new("Sol",'SOLIDIFY'); sol.thickness=0.006; sol.offset=0

# materiali: 3 colori (un pezzo ciascuno) + seam ribbons
def mat(nm,col,emis=0.0):
    m=bpy.data.materials.new(nm); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*col,1.0)
    b.inputs["Roughness"].default_value=0.42
    if emis>0:
        b.inputs["Emission Color"].default_value=(*col,1.0)
        b.inputs["Emission Strength"].default_value=emis
    return m
cols=[(0.12,0.30,0.42),(0.40,0.20,0.12),(0.20,0.36,0.16)]
for c in cols: ob.data.materials.append(mat(f"P{cols.index(c)}",c))
FP=K*(NA-1)
for k,p in enumerate(ob.data.polygons):
    p.material_index=min(2,k//FP)
ob.data.update()

mS=mat("SeamMark",(1.0,0.82,0.05),emis=2.5)
for s in seam_marks:
    cu=bpy.data.curves.new("S",'CURVE'); cu.dimensions='3D'
    cu.bevel_depth=0.0030; cu.bevel_resolution=3
    sp=cu.splines.new('POLY'); sp.points.add(len(s)-1)
    for j,pp in enumerate(s): sp.points[j].co=(pp.x,pp.y,pp.z,1.0)
    so=bpy.data.objects.new("SeamMark",cu); bpy.context.collection.objects.link(so)
    so.data.materials.append(mS)

bpy.ops.mesh.primitive_plane_add(size=4,location=(0.1,0,-0.02))
fl=bpy.context.active_object; fl.data.materials.append(mat("Floor",(0.05,0.05,0.06)))
def area(nm,e,sz,loc):
    bpy.ops.object.light_add(type='AREA',location=loc)
    L=bpy.context.active_object; L.name=nm; L.data.energy=e; L.data.size=sz
    d=Vector((0.1,0,0.1))-Vector(loc)
    L.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
area("K",520,1.5,(-0.9,-1.2,1.3)); area("F",130,2.6,(1.2,-0.9,0.7))
area("R",330,0.8,(0.1,1.3,1.1))
w=bpy.context.scene.world; w.use_nodes=True
wb=w.node_tree.nodes.get("Background")
wb.inputs[0].default_value=(0.02,0.02,0.03,1); wb.inputs[1].default_value=0.07

result={"seam1_gap_mm":round(gap1*1000,4),"seam2_gap_mm":round(gap2*1000,4),
        "welded":welded,"components":comp,"nonmanifold":nonman,
        "bbox_xyz_m":bbox,"pieces":len(PLANES),"planes":PLANES}
"""

if __name__ == "__main__":
    print("=" * 60)
    print("ASSEMBLY KERNEL — composizione 3D: 3 pezzi curvi -> forma complessa")
    print("=" * 60)
    r = blender(BUILD, timeout=120)
    if r:
        print("  metriche:", r)
        render(f"{RENDER_DIR}/compose3d_iso.png", (0.85, -0.85, 0.55))
        render(f"{RENDER_DIR}/compose3d_top.png", (0.10, -0.30, 1.05))
    print("Done.")
