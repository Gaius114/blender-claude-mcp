"""
STITCH ENGINE — Prototipo di validazione
=========================================
Valida il paradigma "boundary-loop socket": forme cave (shell con bocche
aperte) unite lungo i bordi aperti tramite bridge/loft (NON boolean),
in serie e con un branch da PORTA LATERALE (bordo aperto non di estremita').

Claim da validare:
  1. unione di forme cave via bordo aperto, senza chiudere le forme
  2. in serie -> un'unica forma complessa manifold
  3. raggi diversi alle bocche  -> la "superficie di giuntura" e' un tronco
  4. ad angolo (la normale del docking frame = "angolo di giuntura")
  5. branch da apertura laterale (non end-cap) = caso difficile

Validazione = multi-vista (3 angoli) + check manifold/normali, verdetto onesto.
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


def render_view(path, cam_loc, tgt, w=1100, h=850, samples=48, exposure=-0.5):
    code = f"""
import bpy
from mathutils import Vector
cam = bpy.data.objects.get("PVCam")
if cam is None:
    c = bpy.data.cameras.new("PVCam"); cam = bpy.data.objects.new("PVCam", c)
    bpy.context.collection.objects.link(cam)
cam.location = {tuple(cam_loc)}
d = Vector({tuple(tgt)}) - cam.location
cam.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
cam.data.lens = 50
bpy.context.scene.camera = cam
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.eevee.taa_render_samples = {samples}
try: sc.eevee.use_raytracing = True
except Exception: pass
sc.render.resolution_x = {w}; sc.render.resolution_y = {h}
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = {exposure}
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
        print(f"  view -> {path}")
        return True
    print("  view FALLITA")
    return False


# ─────────────────────────────────────────────────────────────────────────────
BUILD = r"""
import bpy, bmesh, math
from mathutils import Vector, Quaternion, Matrix

# pulizia
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.objects):
    for d in list(blk):
        try: blk.remove(d)
        except Exception: pass

bm = bmesh.new()
N = 24  # vertici per bocca circolare (div. per 4)

def ring(C, T, U, r, n=N):
    # anello di n verts nel piano (U, W=T x U) centrato in C, raggio r
    W = T.cross(U).normalized()
    vs = []
    for j in range(n):
        a = 2.0 * math.pi * j / n
        p = C + U * (r * math.cos(a)) + W * (r * math.sin(a))
        vs.append(bm.verts.new(p))
    return vs

def bridge(ra, rb):
    # quad band fra due anelli stesso conteggio, index-aligned (no twist)
    n = len(ra)
    for j in range(n):
        nj = (j + 1) % n
        bm.faces.new([ra[j], ra[nj], rb[nj], rb[j]])

def module(C0, T0, U0, length, r0, r1, bend_deg, bend_axis, K):
    # genera una shell-tubo: spine con curvatura costante 'bend' su 'bend_axis',
    # frame trasportato (anti-twist), anelli bridgeati fra loro.
    # ritorna (ring_start, ring_end, C_end, T_end, U_end)
    T = T0.normalized()
    U = (U0 - T * U0.dot(T)).normalized()
    C = C0.copy()
    total = math.radians(bend_deg)
    rings = []
    for i in range(K + 1):
        s = i / K
        r = r0 + (r1 - r0) * s
        rings.append(ring(C, T, U, r))
        if i < K:
            step = length / K
            C = C + T * step
            if abs(total) > 1e-9:
                q = Quaternion(bend_axis.normalized(), total / K)
                T = (q @ T).normalized()
                U = (q @ U).normalized()
                U = (U - T * U.dot(T)).normalized()
    for a, b in zip(rings[:-1], rings[1:]):
        bridge(a, b)
    return rings[0], rings[-1], C, T, U

def stitch(ra, rb):
    # UNISCE due bocche aperte indipendenti (l'operazione sotto test)
    bridge(ra, rb)

# ── SERIE: 3 moduli cavi, raggi e angoli diversi ────────────────────────────
C = Vector((0, 0, 0)); T = Vector((0, 0, 1)); U = Vector((1, 0, 0))
s0, eA, C, T, U = module(C, T, U, 1.10, 0.30, 0.34,   0,  Vector((0,1,0)),  9)

# docking modulo B: gap + rotazione (= "angolo di giuntura"); U ruotato con T
GAP = 0.06
qB = Quaternion(Vector((0,1,0)), math.radians(38))
Cb = C + T * GAP
Tb = (qB @ T).normalized()
Ub = (qB @ U).normalized()
sB, eB, C, T, U = module(Cb, Tb, Ub, 1.30, 0.30, 0.255, 22, Vector((0,1,0)), 13)
stitch(eA, sB)                       # bocca A.out (r0.34) <-> B.in (r0.30): tronco

qC = Quaternion(Vector((1,0,0)), math.radians(-30))
Cc = C + T * GAP
Tc = (qC @ T).normalized()
Uc = (qC @ U).normalized()
sC, eC, C, T, U = module(Cc, Tc, Uc, 1.05, 0.255, 0.30, -18, Vector((0,1,0)), 11)
stitch(eB, sC)

# ── BRANCH da PORTA LATERALE (bordo aperto NON di estremita') ────────────────
# Ricostruisco un tratto-madre con una finestra: ometto le facce di un patch
# (ia..ib) x (ja..jb). Il bordo del buco e' un loop rettangolare deterministico
# a cui stitcho la bocca di un ramo (stesso conteggio => no triangolazione).
Cm = Vector((0.0, 0.0, -1.30)); Tm = Vector((0,0,1)); Um = Vector((1,0,0))
M_I, M_J = 14, N
rad_m = 0.34
grid = []
for i in range(M_I + 1):
    Ci = Cm + Tm * (i * (1.30 / M_I))
    grid.append(ring(Ci, Tm, Um, rad_m))
ia, ib = 6, 9        # span lungo la spine
ja, jb = 4, 10       # span attorno (apertura laterale)
for i in range(M_I):
    for j in range(M_J):
        if ia <= i < ib and ja <= j < jb:
            continue                 # finestra: niente parete = bordo aperto
        nj = (j + 1) % M_J
        bm.faces.new([grid[i][j], grid[i][nj],
                      grid[i+1][nj], grid[i+1][j]])
stitch(s0, grid[-1])                  # collega la madre alla serie (in serie)

# bordo ordinato della finestra (loop rettangolare)
port = []
for j in range(ja, jb):     port.append(grid[ia][j])
for i in range(ia, ib):     port.append(grid[i][jb])
for j in range(jb, ja, -1): port.append(grid[ib][j])
for i in range(ib, ia, -1): port.append(grid[i][ja])
PN = len(port)                       # conteggio bocca del ramo = PN (match esatto)

# ramo: bocca iniziale = loop NON circolare con PN verts allineato alla porta;
# poi lo "morfo" verso una bocca circolare e via in diagonale (cavo, aperto).
cx = sum(v.co for v in port[:-0] if True or v) if False else None
pc = Vector((0,0,0))
for v in port: pc += v.co
pc /= PN
out_dir = (pc - Cm); out_dir.z = 0.0
out_dir = out_dir.normalized()
Ub2 = Vector((0,0,1))
def ring_named(C, T, Uax, r, n):
    W = T.cross(Uax).normalized()
    vs = []
    for j in range(n):
        a = 2.0 * math.pi * j / n
        vs.append(bm.verts.new(C + Uax*(r*math.cos(a)) + W*(r*math.sin(a))))
    return vs
br_rings = [port]
steps = 7
for k in range(1, steps + 1):
    s = k / steps
    Ck = pc + out_dir * (0.10 + 0.55 * s)
    rk = 0.16 + 0.02 * s
    br_rings.append(ring_named(Ck, out_dir, Ub2, rk, PN))
for a, b in zip(br_rings[:-1], br_rings[1:]):
    bridge(a, b)

# ── Finalizza: una sola mesh, normali coerenti, estremita' LASCIATE APERTE ───
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new("StitchProto")
bm.to_mesh(me)
ob = bpy.data.objects.new("StitchProto", me)
bpy.context.collection.objects.link(ob)

# diagnostica manifold / bordi aperti (atteso: solo le bocche volute)
bm2 = bmesh.new(); bm2.from_mesh(me)
boundary_edges = sum(1 for e in bm2.edges if len(e.link_faces) == 1)
nonmanifold = sum(1 for e in bm2.edges if len(e.link_faces) > 2)
bm2.free()

for p in ob.data.polygons:
    p.use_smooth = True
sub = ob.modifiers.new("Sub", 'SUBSURF'); sub.levels = 1; sub.render_levels = 2

# materiale clay bicolore: interno piu' scuro per leggere il "cavo aperto"
m = bpy.data.materials.new("Clay"); m.use_nodes = True
b = m.node_tree.nodes.get("Principled BSDF")
b.inputs["Base Color"].default_value = (0.30, 0.22, 0.18, 1.0)
b.inputs["Roughness"].default_value = 0.55
ob.data.materials.append(m)
mi = bpy.data.materials.new("Inner"); mi.use_nodes = True
bi = mi.node_tree.nodes.get("Principled BSDF")
bi.inputs["Base Color"].default_value = (0.5, 0.1, 0.08, 1.0)
bi.inputs["Roughness"].default_value = 0.6
ob.data.materials.append(mi)
ob.data.polygons.foreach_set("material_index",
    [1 if p.normal.dot((p.center - ob.location)) < 0 else 0
     for p in ob.data.polygons])
ob.data.update()

# studio minimale
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -2.0))
fl = bpy.context.active_object
fm = bpy.data.materials.new("Floor"); fm.use_nodes = True
fm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.04,0.04,0.05,1)
fl.data.materials.append(fm)

def area(nm, e, sz, loc, col=(1,0.96,0.9)):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object; L.name = nm
    L.data.energy = e; L.data.size = sz; L.data.color = col
    d = Vector((0,0,0.2)) - Vector(loc)
    L.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
area("K", 900, 6, (-4,-5,5)); area("F", 220, 9, (5,-3,2), (0.85,0.9,1.0))
area("R", 600, 3, (0,5,4))
w = bpy.context.scene.world; w.use_nodes = True
wb = w.node_tree.nodes.get("Background")
wb.inputs[0].default_value = (0.02,0.02,0.03,1); wb.inputs[1].default_value = 0.10

result = {
    "verts": len(me.vertices), "faces": len(me.polygons),
    "boundary_edges": boundary_edges,   # bordi aperti totali
    "nonmanifold_edges": nonmanifold,   # deve essere 0
    "port_count": PN,
}
"""

if __name__ == "__main__":
    print("=" * 56)
    print("STITCH ENGINE — prototipo di validazione")
    print("=" * 56)
    r = blender(BUILD, timeout=120)
    print("  build ->", r)
    if r:
        render_view(f"{RENDER_DIR}/stitch_A.png", (5.0, -5.0, 1.0), (0.2, 0, 0.0))
        render_view(f"{RENDER_DIR}/stitch_B.png", (0.2, -6.0, 2.2), (0.2, 0, 0.2))
        render_view(f"{RENDER_DIR}/stitch_C.png", (-0.3, 0.3, 5.2), (0.0, 0, 0.0))
    print("Done.")
