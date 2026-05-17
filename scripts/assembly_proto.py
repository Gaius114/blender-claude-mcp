"""
ASSEMBLY KERNEL — Prototipo di validazione
============================================
Valida la disciplina: ogni pezzo autorato nel SUO frame locale (matrice
rigida local->global), ma le CUCITURE sono UNA curva condivisa posseduta
dall'assieme in coordinate globali. La base globale = il "last".

Claim:
  - last (superficie master) in coordinate globali, origine = base globale
  - 2 pannelli (vamp, quarter) autorati in frame LOCALI DIVERSI
  - condividono UNA SeamCurve globale -> bordi coincidenti, seam saldabile
  - controllo negativo: stessi pannelli SENZA curva condivisa (ognuno autora
    il bordo nel proprio locale) -> gap misurabile

Validazione = metriche oggettive (gap max, vertici saldati, manifold) +
render comparativo bbox-framed GOOD vs BAD.
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


def render(path, w=1280, h=820, samples=48):
    code = f"""
import bpy
from mathutils import Vector
sc = bpy.context.scene
# bbox di TUTTI i mesh -> framing che contiene l'intero assieme (fix scorso)
mins = Vector(( 1e9, 1e9, 1e9)); maxs = Vector((-1e9,-1e9,-1e9))
for o in bpy.data.objects:
    if o.type != 'MESH': continue
    for c in o.bound_box:
        wc = o.matrix_world @ Vector(c)
        mins.x=min(mins.x,wc.x); mins.y=min(mins.y,wc.y); mins.z=min(mins.z,wc.z)
        maxs.x=max(maxs.x,wc.x); maxs.y=max(maxs.y,wc.y); maxs.z=max(maxs.z,wc.z)
ctr = (mins+maxs)*0.5
# bbox dei soli ASSIEMI (ignora il floor gigante)
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
cam.location = ctr + Vector((diag*0.35, -diag*0.85, diag*0.55))
d = ctr - cam.location
cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
cam.data.lens = 55
bpy.context.scene.camera = cam
# rinforza luci (oggetti piccoli) ed esposizione
for L in bpy.data.objects:
    if L.type == 'LIGHT':
        L.data.energy *= 6.0
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = {samples}
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = 0.3
sc.render.use_compositing = False
import tempfile, base64, os
tmp = tempfile.mktemp(suffix=".png"); sc.render.filepath = tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64 = base64.b64encode(f.read()).decode()
os.remove(tmp)
result = {{"b64": b64}}
"""
    r = blender(code, timeout=180)
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
            bpy.data.cameras, bpy.data.objects):
    for d in list(blk):
        try: blk.remove(d)
        except Exception: pass

# ── LAST: superficie master S(t,a) in coordinate GLOBALI (base = origine) ────
STATIONS = [
    (0.000, 0.034, 0.030, 0.085),  # tallone
    (0.080, 0.045, 0.020, 0.095),  # collo del piede
    (0.160, 0.052, 0.017, 0.075),  # avampiede
    (0.220, 0.046, 0.020, 0.055),  # toe box
    (0.270, 0.020, 0.030, 0.043),  # punta
]
NS = len(STATIONS)
E  = 2.4

def lerp(a, b, s): return a + (b - a) * s

def last_S(t, a):
    # t in [0,1] tallone->punta ; a angolo sezione (squircle Y-Z)
    f = max(0.0, min(0.999999, t)) * (NS - 1)
    i = int(f); s = f - i
    x0, w0, b0, p0 = STATIONS[i]
    x1, w1, b1, p1 = STATIONS[min(i + 1, NS - 1)]
    x  = lerp(x0, x1, s)
    hw = lerp(w0, w1, s)
    zb = lerp(b0, b1, s)
    zt = lerp(p0, p1, s)
    cz = (zb + zt) * 0.5
    hz = (zt - zb) * 0.5
    ca = math.cos(a); sa = math.sin(a)
    y = math.copysign(abs(ca) ** (2.0 / E), ca) * hw
    z = cz + math.copysign(abs(sa) ** (2.0 / E), sa) * hz
    return Vector((x, y, z))

# ── FRAME locale su superficie (matrice RIGIDA local->global) ────────────────
def surface_frame(t, a):
    o  = last_S(t, a)
    dt = (last_S(t + 1e-4, a) - last_S(t - 1e-4, a)).normalized()
    da = (last_S(t, a + 1e-4) - last_S(t, a - 1e-4)).normalized()
    n  = dt.cross(da).normalized()
    da = n.cross(dt).normalized()       # ri-ortogonalizza (frame ortonormale)
    R = Matrix((dt, da, n)).transposed().to_4x4()   # colonne = assi locali
    M = Matrix.Translation(o) @ R
    return M                            # rigida: rotazione + traslazione

# banda angolare superiore (la "semi-arco" instep, lontano dai poli)
A_LO = math.pi / 2 - 1.15
A_HI = math.pi / 2 + 1.15
T_SEAM = 0.5
NT_HALF = 9       # campioni lungo t per meta'
NA = 16           # campioni lungo l'arco condiviso

# ── SeamCurve: UNA curva globale posseduta dall'assieme, sul last ────────────
def seam_curve(j):
    a = lerp(A_LO, A_HI, j / (NA - 1))
    return last_S(T_SEAM, a)            # singola definizione condivisa

def build_panel(bm, M, t0, t1, seam_mode, seam_shift=0.0):
    # Pannello autorato in coord LOCALI (M^-1 . global); placement = M (rigida).
    # seam_mode: 'shared' -> bordo = SeamCurve condivisa
    #            'own'    -> bordo autorato nel PROPRIO locale (no condivisione)
    Mi = M.inverted()
    grid = []
    seam_global = []
    for i in range(NT_HALF):
        t = lerp(t0, t1, i / (NT_HALF - 1))
        is_seam = (abs(t - T_SEAM) < 1e-9)
        row = []
        for j in range(NA):
            if is_seam and seam_mode == 'shared':
                Pg = seam_curve(j)                       # curva UNICA condivisa
            elif is_seam and seam_mode == 'own':
                a = lerp(A_LO + seam_shift, A_HI + seam_shift,
                         j / (NA - 1))                   # bordo nel proprio locale
                Pg = last_S(T_SEAM, a)
            else:
                a = lerp(A_LO, A_HI, j / (NA - 1))
                Pg = last_S(t, a)
            loc = Mi @ Pg                # autorato in LOCALE
            row.append(bm.verts.new(M @ loc))   # assemblato in GLOBALE
            if is_seam:
                seam_global.append((M @ loc).copy())
        grid.append(row)
    bm.verts.ensure_lookup_table()
    for i in range(NT_HALF - 1):
        for j in range(NA - 1):
            bm.faces.new([grid[i][j], grid[i][j+1],
                          grid[i+1][j+1], grid[i+1][j]])
    return seam_global

def make_assembly(name, seam_mode, x_off):
    bm = bmesh.new()
    # frame LOCALI DIVERSI: vamp ancorato alla punta, quarter al tallone
    M_v = surface_frame(0.82, math.pi / 2)
    M_q = surface_frame(0.18, math.pi / 2)
    sg_v = build_panel(bm, M_v, T_SEAM, 1.0, seam_mode, +0.00)  # vamp
    sg_q = build_panel(bm, M_q, 0.0, T_SEAM, seam_mode, +0.14)  # quarter
    # metrica: distanza max fra i due bordi-seam (prima di saldare)
    gap = max((sg_v[j] - sg_q[j]).length for j in range(len(sg_v)))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location.x = x_off
    bpy.context.collection.objects.link(ob)
    # saldatura del seam (merge by distance piccolissimo)
    bm2 = bmesh.new(); bm2.from_mesh(me)
    v_before = len(bm2.verts)
    bmesh.ops.remove_doubles(bm2, verts=bm2.verts, dist=1e-5)
    welded = v_before - len(bm2.verts)
    boundary = sum(1 for e in bm2.edges if len(e.link_faces) == 1)
    nonman   = sum(1 for e in bm2.edges if len(e.link_faces) > 2)
    bm2.to_mesh(me); bm2.free(); me.update()
    for p in me.polygons:
        p.use_smooth = True
    return ob, {"seam_gap_max_mm": round(gap * 1000, 3),
                "welded_verts": welded, "expected_weld": NA,
                "boundary_edges": boundary, "nonmanifold": nonman}

# GOOD = curva condivisa ; BAD = ogni pannello autora il proprio bordo
ob_good, m_good = make_assembly("Asm_SHARED",  'shared', 0.0)
ob_bad,  m_bad  = make_assembly("Asm_NOSHARE", 'own',    0.45)

# materiali: vamp/quarter due tinte -> il seam si vede
def mat(nm, col):
    m = bpy.data.materials.new(nm); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1.0)
    b.inputs["Roughness"].default_value = 0.5
    return m
mv = mat("Vamp", (0.32, 0.20, 0.14))
mq = mat("Quarter", (0.16, 0.26, 0.34))
for ob in (ob_good, ob_bad):
    ob.data.materials.append(mv); ob.data.materials.append(mq)
    # prime NT_HALF-1 file di quad = vamp(mat0); resto = quarter(mat1)
    fpr = (NT_HALF - 1) * (NA - 1)
    for k, p in enumerate(ob.data.polygons):
        p.material_index = 0 if k < fpr else 1
    ob.data.update()

# studio
bpy.ops.mesh.primitive_plane_add(size=20, location=(0.2, 0, -0.05))
fl = bpy.context.active_object
fm = mat("Floor", (0.04, 0.04, 0.05)); fl.data.materials.append(fm)
def area(nm, e, sz, loc):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object; L.name = nm
    L.data.energy = e; L.data.size = sz
    d = Vector((0.2,0,0.05)) - Vector(loc)
    L.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
area("K", 300, 3, (-2,-3,3)); area("F", 80, 5, (3,-2,1.5))
area("R", 200, 1.5, (0.2,3,2.5))
w = bpy.context.scene.world; w.use_nodes = True
wb = w.node_tree.nodes.get("Background")
wb.inputs[0].default_value = (0.02,0.02,0.03,1); wb.inputs[1].default_value = 0.10

result = {"GOOD (curva condivisa)": m_good,
          "BAD  (no condivisione)": m_bad}
"""

if __name__ == "__main__":
    print("=" * 58)
    print("ASSEMBLY KERNEL — last globale + frame locali + seam condivisa")
    print("=" * 58)
    r = blender(BUILD, timeout=120)
    if r:
        for k, v in r.items():
            print(f"  {k}: {v}")
        render(f"{RENDER_DIR}/assembly_proto.png", w=1280, h=820, samples=56)
    print("Done.")
