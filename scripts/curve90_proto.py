"""
ASSEMBLY KERNEL — Curvatura forte (90 gradi) (validazione)
===========================================================
Spinge il ragionamento: i pannelli finora erano ~piani (1 frame rigido
bastava). Un pannello che curva 90 gradi NON e' autorabile con un frame
singolo: serve un CAMPO DI FRAME (parallel transport, anti-drift) lungo
una spine LOCALE. Ma:
  - la SeamCurve condivisa (continuita' di posizione) resta invariata
  - il placement local->global resta UNA matrice rigida
  - la curvatura vive SOLO nel frame-field locale
I tre livelli sono ortogonali e si compongono.

GOOD: pannello B con frame-field PT su arco 90 -> bend ~90, seam 0, 1 mesh.
BAD : stesso B con FRAME SINGOLO -> resta piatto (bend ~0) pur avendo la
      seam condivisa OK -> isola che la curvatura richiede il frame-field.

Validazione = metriche oggettive (gap, componenti, manifold, bend misurato,
drift normali) + render leggibile. Scala: metri. Engine: BLENDER_EEVEE.
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

NA = 11        # campioni lungo la larghezza (Y) della cucitura
K  = 16        # passi lungo l'arco del pannello curvo
RB = 0.13      # raggio dell'arco locale del pannello B
W  = 0.16      # larghezza pannelli (lungo Y)
BEND = math.radians(90.0)

def frame_to_M(o, ex, ey, ez):
    R = Matrix((ex, ey, ez)).transposed().to_4x4()
    return Matrix.Translation(o) @ R

# placement RIGIDI distinti per i due pannelli (frame locali diversi)
M_A = frame_to_M(Vector((0.0, 0.0, 0.0)),
                 Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1)))
# B: origine spostata e ruotata -> frame locale chiaramente diverso
qB = Quaternion(Vector((0,0,1)), math.radians(35))
M_B = frame_to_M(Vector((0.02, 0.0, 0.0)),
                 qB @ Vector((1,0,0)), qB @ Vector((0,1,0)), Vector((0,0,1)))

# ── SeamCurve UNICA in GLOBALE = il bordo iniziale (theta=0) di B ────────────
# In locale-B: punti (0, y, 0), y in [-W/2, W/2]. In globale: M_B @ punto.
def seam_curve(j):
    y = -W/2 + W * (j/(NA-1))
    return M_B @ Vector((0.0, y, 0.0))

def parallel_transport(pts):
    n=len(pts); fr=[None]*n
    T0=(pts[1]-pts[0]).normalized()
    up=Vector((0,1,0))
    if abs(T0.dot(up))>0.99: up=Vector((1,0,0))
    Ncur=(up - T0*T0.dot(up)).normalized()
    fr[0]=(T0,Ncur,T0.cross(Ncur).normalized())
    for i in range(1,n):
        Tp,Np,Bp=fr[i-1]
        Tc=(pts[min(i+1,n-1)]-pts[i-1]).normalized() if 0<i<n-1 else (pts[i]-pts[i-1]).normalized()
        ax=Tp.cross(Tc)
        if ax.length>1e-9:
            ax.normalize()
            ang=math.acos(max(-1,min(1,Tp.dot(Tc))))
            Nc=(Quaternion(ax,ang) @ Np)
        else:
            Nc=Np.copy()
        Nc=(Nc - Tc*Tc.dot(Nc)).normalized()
        Bc=Tc.cross(Nc).normalized()
        Nc=Bc.cross(Tc).normalized()
        fr[i]=(Tc,Nc,Bc)
    return fr

def build(name, curved, xoff):
    bm=bmesh.new()

    # ---- Pannello B: arco 90 in LOCALE, autorato con frame-field o singolo ---
    # spine locale: L(t)= (RB*sin a, 0, RB*(1-cos a)), a in [0,BEND]
    spine=[]
    for i in range(K+1):
        a=BEND*i/K
        spine.append(Vector((RB*math.sin(a), 0.0, RB*(1.0-math.cos(a)))))
    if curved:
        FR=parallel_transport(spine)              # CAMPO di frame (anti-drift)
    else:
        # FRAME SINGOLO: usa il frame iniziale per tutti i passi e avanza
        # in linea retta -> il pannello resta PIATTO (perde la curvatura)
        T0=(spine[1]-spine[0]).normalized()
        N0=Vector((0,1,0)); B0=T0.cross(N0).normalized()
        arclen=RB*BEND
        spine=[Vector((0,0,0))+T0*(arclen*i/K) for i in range(K+1)]
        FR=[(T0,N0,B0)]*(K+1)

    ringsB=[]
    for pt,(T,Nn,Bn) in zip(spine,FR):
        # larghezza lungo l'asse 'N' del frame (Y locale a theta=0)
        row=[]
        for j in range(NA):
            y=-W/2 + W*(j/(NA-1))
            P_localB = pt + Nn*y
            row.append(bm.verts.new(M_B @ P_localB))   # locale -> globale
        ringsB.append(row)
    for i in range(K):
        for j in range(NA-1):
            bm.faces.new([ringsB[i][j],ringsB[i][j+1],
                          ringsB[i+1][j+1],ringsB[i+1][j]])

    # ---- Pannello A: piatto, bordo = SeamCurve condivisa (autorato in A) -----
    Mi=M_A.inverted()
    NTA=5
    ringsA=[]
    for i in range(NTA):
        s=i/(NTA-1)
        row=[]
        for j in range(NA):
            if i==NTA-1:
                Pg=seam_curve(j)                  # bordo = curva condivisa
            else:
                # interno piatto che si estende via dalla cucitura
                base=seam_curve(j)
                Pg=base + Vector((-0.16,0,0))*(1.0-s)
            row.append(bm.verts.new(M_A @ (Mi @ Pg)))
        ringsA.append(row)
    for i in range(NTA-1):
        for j in range(NA-1):
            bm.faces.new([ringsA[i][j],ringsA[i][j+1],
                          ringsA[i+1][j+1],ringsA[i+1][j]])

    # metrica seam: distanza max fra bordo-A (ultima riga) e B (prima riga)
    segA=[ringsA[-1][j].co.copy() for j in range(NA)]
    segB=[ringsB[0][j].co.copy()  for j in range(NA)]
    gap=max((segA[j]-segB[j]).length for j in range(NA))

    # bend misurato di B: angolo fra tangente iniziale e finale della spine
    t_first=(ringsB[1][0].co-ringsB[0][0].co).normalized()
    t_last =(ringsB[-1][0].co-ringsB[-2][0].co).normalized()
    bend_deg=math.degrees(math.acos(max(-1,min(1,t_first.dot(t_last)))))

    me=bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob=bpy.data.objects.new(name,me); ob.location.x=xoff
    bpy.context.collection.objects.link(ob)

    bm2=bmesh.new(); bm2.from_mesh(me)
    vb=len(bm2.verts)
    bmesh.ops.remove_doubles(bm2,verts=bm2.verts,dist=1e-5)
    welded=vb-len(bm2.verts)
    nonman=sum(1 for e in bm2.edges if len(e.link_faces)>2)
    # drift normali lungo B: max angolo fra normali-anello consecutive
    bm2.normal_update()
    bm2.to_mesh(me); bm2.free(); me.update()
    # componenti
    bm3=bmesh.new(); bm3.from_mesh(me)
    seen=set(); comp=0
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
    for p in me.polygons: p.use_smooth=True
    sol=ob.modifiers.new("Sol",'SOLIDIFY'); sol.thickness=0.006; sol.offset=0
    return ob,{"seam_gap_mm":round(gap*1000,4),
               "panelB_bend_deg":round(bend_deg,2),
               "welded":welded,"expected":NA,
               "components":comp,"nonmanifold":nonman}

obG,mG=build("Asm_CURVED", True,  0.00)   # frame-field PT
obB,mB=build("Asm_FLAT",   False, 0.45)   # frame singolo (controllo)

def mat(nm,col,emis=0.0):
    m=bpy.data.materials.new(nm); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(*col,1.0)
    b.inputs["Roughness"].default_value=0.45
    if emis>0:
        b.inputs["Emission Color"].default_value=(*col,1.0)
        b.inputs["Emission Strength"].default_value=emis
    return m
mA=mat("PanelA",(0.12,0.30,0.40)); mB_=mat("PanelB",(0.42,0.18,0.10))
FB=K*(NA-1)   # facce pannello B
for ob in (obG,obB):
    ob.data.materials.append(mB_); ob.data.materials.append(mA)
    for k,p in enumerate(ob.data.polygons):
        p.material_index=0 if k<FB else 1
    ob.data.update()

# SeamCurve come nastro giallo (sul GOOD) per vederla
mS=mat("Seam",(1.0,0.8,0.05),emis=2.5)
cu=bpy.data.curves.new("SeamC",'CURVE'); cu.dimensions='3D'
cu.bevel_depth=0.0030; cu.bevel_resolution=3
sp=cu.splines.new('POLY'); sp.points.add(NA-1)
for j in range(NA):
    p=seam_curve(j); sp.points[j].co=(p.x,p.y,p.z,1.0)
so=bpy.data.objects.new("SeamMark",cu); bpy.context.collection.objects.link(so)
so.data.materials.append(mS)

bpy.ops.mesh.primitive_plane_add(size=4,location=(0.2,0,-0.02))
fl=bpy.context.active_object; fl.data.materials.append(mat("Floor",(0.05,0.05,0.06)))
def area(nm,e,sz,loc):
    bpy.ops.object.light_add(type='AREA',location=loc)
    L=bpy.context.active_object; L.name=nm; L.data.energy=e; L.data.size=sz
    d=Vector((0.2,0,0.05))-Vector(loc)
    L.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
area("K",600,1.6,(-1.1,-1.4,1.5)); area("F",150,3,(1.4,-1.0,0.8))
area("R",380,0.9,(0.2,1.5,1.3))
w=bpy.context.scene.world; w.use_nodes=True
wb=w.node_tree.nodes.get("Background")
wb.inputs[0].default_value=(0.02,0.02,0.03,1); wb.inputs[1].default_value=0.07

result={"CURVED (frame-field PT)":mG,"FLAT (frame singolo)":mB}
"""

if __name__ == "__main__":
    print("=" * 60)
    print("ASSEMBLY KERNEL — curvatura 90 gradi (frame-field vs singolo)")
    print("=" * 60)
    r = blender(BUILD, timeout=120)
    if r:
        for k, v in r.items():
            print(f"  {k}: {v}")
        render(f"{RENDER_DIR}/curve90_iso.png", (0.80, -0.95, 0.55))
        render(f"{RENDER_DIR}/curve90_side.png", (0.05, -1.05, 0.18))
    print("Done.")
