"""
COMBAT BOOT (anfibio) via assembly_kernel — render prodotto
============================================================
Estende il pattern VALIDATO di boot_kernel.py:
  - last del PIEDE identico (eredita il manifold provato)
  - + GAMBALE: il quarter esteso verso l'alto (ricetta continua ->
    NESSUNA cucitura inventata; piano _good_boot resta valido)
  - spine collar->gamba->piega-caviglia->piede->punta + parallel
    transport (la piega ~90 alla caviglia e' caso validato in memoria)
  - banda angolare t-dipendente: apertura al fondo (feather/sola) sul
    piede, ruota verso il fronte (throat/lacci) sulla gamba
  - pannelli quarter/vamp/toecap via panel_on_master, cuciture CONDIVISE
  - finalize(weld) -> validate() GATE: 1 componente / 0 non-manifold

Scala: metri. Engine: BLENDER_EEVEE (Blender 5.1).
"""

import urllib.request, json, base64, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLENDER_URL = "http://localhost:7234"
RENDER_DIR  = "D:/blender-claude/renders"


def blender(code, timeout=180):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout + 20)
        r    = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, "BODY:", e.read().decode(errors="replace")[:2400])
        return None
    if "error" in r:
        print("ERR:", r["error"][:2400])
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

import math
def lerp(a,b,s): return a + (b-a)*s
def smooth(s):
    s = max(0.0, min(1.0, s)); return s*s*(3-2*s)
def keyed(t, keys):
    # keys = [(t0,v0),(t1,v1),...] ordinati -> interp lineare
    if t <= keys[0][0]:  return keys[0][1]
    if t >= keys[-1][0]: return keys[-1][1]
    for i in range(len(keys)-1):
        a,va = keys[i]; b,vb = keys[i+1]
        if a <= t <= b:
            return lerp(va, vb, (t-a)/(b-a))
    return keys[-1][1]

# ── SPINE unico (collar -> gamba -> PIEGA ~90 -> piede -> punta) ────────────
# planare in XZ (Y=0) -> parallel transport tiene B ~ Y, N ruota in XZ.
# Nodi fitti nella piega = caviglia liscia (90 gradi = caso validato).
spine = [Vector(p) for p in (
    (-0.016,0,0.205),(-0.013,0,0.180),(-0.010,0,0.156),   # gamba
    (-0.007,0,0.132),(-0.004,0,0.110),(-0.001,0,0.090),   # gamba bassa
    ( 0.003,0,0.075),(0.010,0,0.062),(0.021,0,0.052),     # PIEGA caviglia
    ( 0.035,0,0.046),(0.058,0,0.043),(0.090,0,0.041),     # heel->arch
    ( 0.130,0,0.040),(0.170,0,0.039),(0.205,0,0.038),     # ball
    ( 0.236,0,0.037),(0.260,0,0.036),                     # toe
)]
NSP = len(spine)
FR  = ak.parallel_transport(spine, up_hint=Vector((1,0,0)))
def spine_at(t):
    f = max(0.0, min(0.999999, t)) * (NSP-1)
    i = int(f); s = f - i
    P = spine[i].lerp(spine[min(i+1,NSP-1)], s)
    T0,N0,B0 = FR[i]; T1,N1,B1 = FR[min(i+1,NSP-1)]
    return P, N0.lerp(N1,s).normalized(), B0.lerp(B1,s).normalized()

# ── SEZIONE: mezzo-asse lungo N (hz, antero-post.) e B (hw, larghezza Y) ────
HZ_KEYS = [(0.00,0.057),(0.31,0.060),(0.42,0.058),(0.55,0.050),
           (0.66,0.046),(0.85,0.039),(0.95,0.033),(1.00,0.025)]
HW_KEYS = [(0.00,0.052),(0.31,0.050),(0.42,0.050),(0.55,0.052),
           (0.66,0.053),(0.85,0.055),(0.95,0.041),(1.00,0.017)]
def section(t):
    return keyed(t, HZ_KEYS), keyed(t, HW_KEYS)

# ── BANDA ANGOLARE: gap su -N (g=pi). GAMBA chiusa (tubo), il QUARTER apre
# il fondo (feather) per la suola. Transizione isolata nel quarter.
T_COLLAR = 0.31    # cucitura gamba|quarter (topline/collar) — anello CHIUSO
T_VQ     = 0.62    # vamp | quarter
T_TC     = 0.85    # toecap | vamp
GAP_FOOT = 1.32
T_OPEN   = T_COLLAR + 0.22                  # fine apertura graduale
def half_gap_at(t):
    if t <= T_COLLAR: return 0.0            # gamba/collar = anello chiuso
    if t >= T_OPEN:   return GAP_FOOT
    return GAP_FOOT * smooth((t-T_COLLAR)/(T_OPEN-T_COLLAR))
def band_a(t, r):
    hg = half_gap_at(t)
    return (math.pi + hg) + (2*math.pi - 2*hg) * r
def surf(t, r):
    P, N, B = spine_at(t)
    hz, hw = section(t)
    a = band_a(t, r)
    return P + N * (hz * math.cos(a)) + B * (hw * math.sin(a))

# ── CUCITURE REALI condivise (constant-t), INCLUSO s_collar ────────────────
NR = 36
A = ak.Assembly("CombatBoot")
s_collar = A.seam("s_collar", [surf(T_COLLAR, j/(NR-1)) for j in range(NR)])
s_vq     = A.seam("s_vq",     [surf(T_VQ,     j/(NR-1)) for j in range(NR)])
s_tc     = A.seam("s_tc",     [surf(T_TC,     j/(NR-1)) for j in range(NR)])

def mk(tA, tB):
    def m(r, t):  return surf(lerp(tA, tB, t), r)
    return m

LEATHER = (0.020,0.019,0.019)
# shaft (gambale): collar-top -> s_collar  | tubo quasi chiuso, NT dedicati
A.panel_on_master(mk(0.0, T_COLLAR), NR, 9,
                  edge_t1=s_collar, material=LEATHER)
# quarter: s_collar -> s_vq  | fa la PIEGA + apre il fondo, NT alti
A.panel_on_master(mk(T_COLLAR, T_VQ), NR, 14,
                  edge_t0=s_collar, edge_t1=s_vq, material=LEATHER)
# vamp: s_vq -> s_tc
A.panel_on_master(mk(T_VQ, T_TC), NR, 9,
                  edge_t0=s_vq, edge_t1=s_tc, material=(0.026,0.024,0.024))
# toe-cap: s_tc -> punta
A.panel_on_master(mk(T_TC, 1.0), NR, 7,
                  edge_t0=s_tc, material=(0.020,0.018,0.018))

A.finalize(weld=True)
m = A.validate()
ak.studio_setup()

# ── SUOLA LUG: solido lofted ; bordo SUPERIORE = feather REALE dell'upper ──
# Campiona surf(t,0)/surf(t,1) (i due lati dell'apertura inferiore) -> la
# suola combacia per costruzione con il bordo aperto dell'upper.
import bmesh
Z_GROUND = 0.0
T_S0, T_S1 = T_OPEN - 0.02, 0.985            # range piede della feather
NSEG = 36
def feather_pts(i):
    t  = lerp(T_S0, T_S1, i/(NSEG-1))
    FL = surf(t, 0.0); FR = surf(t, 1.0)
    xc = (FL.x + FR.x) * 0.5
    y_f = max(abs(FL.y), abs(FR.y))
    z_f = min(FL.z, FR.z)
    return xc, y_f, z_f
def outsole_bottom(frac):
    arch = 0.011*math.sin(math.pi*(frac-0.34)/0.30) if 0.34 < frac < 0.64 else 0.0
    lug  = 0.0045 if (int(frac*26) % 2 == 0) else 0.0    # grooves trasversali
    return Z_GROUND + arch + lug

NTOP, NSIDE, NBOT = 5, 5, 9
def sole_ring(i):
    xc, y_f, z_f = feather_pts(i); frac = i/(NSEG-1)
    ov = 1.0
    if i < 3:        ov = lerp(0.55, 1.0, i/3)           # tallone arrotondato
    if i > NSEG-4:   ov = lerp(1.0, 0.45, (i-(NSEG-4))/3)# punta arrotondata
    dx = -0.012 if i == 0 else (0.012 if i == NSEG-1 else 0.0)  # overhang X
    x = xc + dx
    y_f = max(y_f * ov, 0.004)
    w_b = y_f + 0.013
    z_b = outsole_bottom(frac)
    P = []
    for k in range(NTOP):                                # footbed (nascosto)
        s = k/(NTOP-1); y = lerp(y_f, -y_f, s)
        P.append(Vector((x, y, z_f + 0.004*(1-(y/max(y_f,1e-6))**2))))
    for k in range(1, NSIDE+1):                          # fianco sinistro
        s = k/(NSIDE+1)
        P.append(Vector((x, lerp(-y_f, -w_b, math.sin(s*math.pi/2)),
                            lerp(z_f, z_b, s))))
    for k in range(NBOT):                                # fondo
        s = k/(NBOT-1); P.append(Vector((x, lerp(-w_b, w_b, s), z_b)))
    for k in range(1, NSIDE+1):                          # fianco destro
        s = k/(NSIDE+1)
        P.append(Vector((x, lerp(w_b, y_f, math.sin(s*math.pi/2)),
                            lerp(z_b, z_f, s))))
    return P

bm = bmesh.new()
rings = [[bm.verts.new(p) for p in sole_ring(i)] for i in range(NSEG)]
NAR = len(rings[0])
for i in range(NSEG-1):
    for k in range(NAR):
        k2 = (k+1) % NAR
        bm.faces.new([rings[i][k], rings[i][k2],
                      rings[i+1][k2], rings[i+1][k]])
for ring, flip in ((rings[0], True), (rings[-1], False)):
    c = bm.verts.new(sum((v.co for v in ring), Vector())/len(ring))
    for k in range(NAR):
        k2 = (k+1) % NAR
        f = [c, ring[k2], ring[k]] if flip else [c, ring[k], ring[k2]]
        bm.faces.new(f)
bm.normal_update()
me_s = bpy.data.meshes.new("Asm_Sole")
bm.to_mesh(me_s); bm.free()
for p in me_s.polygons: p.use_smooth = True
ob_s = bpy.data.objects.new("Asm_Sole", me_s)
bpy.context.collection.objects.link(ob_s)
mat_s = bpy.data.materials.new("SoleRubber")
mat_s.use_nodes = True
bs = mat_s.node_tree.nodes.get("Principled BSDF")
bs.inputs["Base Color"].default_value = (0.015,0.014,0.014,1.0)
bs.inputs["Roughness"].default_value = 0.85
me_s.materials.append(mat_s)

bs2 = bmesh.new(); bs2.from_mesh(me_s)
sole_nonman = sum(1 for e in bs2.edges if len(e.link_faces) > 2)
bs2.free()

# ── MATERIALI PBR ──────────────────────────────────────────────────────────
def mkmat(name, rgb, rough, metal=0.0, coat=0.0):
    mt = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mt.use_nodes = True
    b = mt.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value = coat
    return mt
M_LEATHER = mkmat("Leather", (0.018,0.016,0.016), 0.52, 0.0, 0.15)
M_RUBBER  = mkmat("SoleRubber2", (0.013,0.012,0.012), 0.82)
M_METAL   = mkmat("EyeletMetal", (0.34,0.34,0.36), 0.34, 1.0)
M_LACE    = mkmat("LaceFabric", (0.035,0.033,0.030), 0.90)
# upper: sostituisci il mosaico del kernel con pelle nera unica
up = A.obj
up.data.materials.clear(); up.data.materials.append(M_LEATHER)
for p in up.data.polygons: p.material_index = 0
ob_s.data.materials.clear(); ob_s.data.materials.append(M_RUBBER)

# ── FRONT-LINE: punto e frame sul davanti del boot (a ~ 0 -> +N) ───────────
def front_at(t):
    hg = half_gap_at(t)
    rf = (math.pi - hg) / (2*math.pi - 2*hg)
    P, N, B = spine_at(t)
    return surf(t, rf), N.normalized(), B.normalized()

def add_between(p0, p1, rad, mat, name):
    p0 = Vector(p0); p1 = Vector(p1); d = p1 - p0
    L = max(d.length, 1e-5)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=rad, depth=L,
        location=(p0+p1)*0.5)
    o = bpy.context.active_object; o.name = name
    o.rotation_euler = d.to_track_quat('Z','Y').to_euler()
    o.data.materials.append(mat)
    for pp in o.data.polygons: pp.use_smooth = True
    return o

def add_torus(center, axis, Rmaj, Rmin, mat, name):
    bpy.ops.mesh.primitive_torus_add(major_radius=Rmaj, minor_radius=Rmin,
        major_segments=16, minor_segments=8, location=center)
    o = bpy.context.active_object; o.name = name
    o.rotation_euler = Vector(axis).to_track_quat('Z','Y').to_euler()
    o.data.materials.append(mat)
    for pp in o.data.polygons: pp.use_smooth = True
    return o

# ── TONGUE: slab di pelle sul davanti (instep -> bassa gamba) ───────────────
T_TT, T_TB = 0.090, 0.800
NTG = 20
tg_bm = bmesh.new(); tg_rows = []
for i in range(NTG):
    t = lerp(T_TT, T_TB, i/(NTG-1))
    Pf, N, B = front_at(t)
    wf = lerp(0.030, 0.044, smooth(i/(NTG-1)))
    end_r = 1.0
    if i == 0:       end_r = 0.55           # estremo superiore arrotondato
    if i == NTG-1:   end_r = 0.80
    c = Pf + N*0.0025
    h = wf*0.5*end_r; th = 0.006
    quad = [c - B*h, c + B*h, c + B*h + N*th, c - B*h + N*th]
    tg_rows.append([tg_bm.verts.new(p) for p in quad])
for i in range(NTG-1):
    for k in range(4):
        k2 = (k+1) % 4
        tg_bm.faces.new([tg_rows[i][k], tg_rows[i][k2],
                         tg_rows[i+1][k2], tg_rows[i+1][k]])
for row, fl in ((tg_rows[0], True), (tg_rows[-1], False)):
    tg_bm.faces.new(row[::-1] if fl else row)
tg_bm.normal_update()
me_tg = bpy.data.meshes.new("Asm_Tongue"); tg_bm.to_mesh(me_tg); tg_bm.free()
for p in me_tg.polygons: p.use_smooth = True
ob_tg = bpy.data.objects.new("Asm_Tongue", me_tg)
bpy.context.collection.objects.link(ob_tg)
me_tg.materials.append(M_LEATHER)

# ── SCALETTA LACCI: campionata per LUNGHEZZA D'ARCO della front-line ───────
# (campionare t uniforme ammasserebbe le rampe nella piega della caviglia).
T_FRONT_HI, T_FRONT_LO = 0.085, 0.795           # collare-front .. vamp/instep
NFINE = 220
ts_fine = [lerp(T_FRONT_HI, T_FRONT_LO, i/NFINE) for i in range(NFINE+1)]
pf_fine = [front_at(t)[0] for t in ts_fine]
cum = [0.0]
for i in range(1, len(pf_fine)):
    cum.append(cum[-1] + (pf_fine[i]-pf_fine[i-1]).length)
total = cum[-1]
def t_at_arc(s):
    for i in range(1, len(cum)):
        if cum[i] >= s:
            f = (s-cum[i-1])/max(cum[i]-cum[i-1],1e-9)
            return lerp(ts_fine[i-1], ts_fine[i], f)
    return ts_fine[-1]
NRUNGS = 9
T_ANKLE = 0.44                                  # > = piede (eyelet), < = gamba (hook)
anchors = []
for k in range(NRUNGS):
    t = t_at_arc(total * k/(NRUNGS-1))
    Pf, N, B = front_at(t)
    hz, hw = section(t)
    off = max(0.017, 0.40*hw)
    if t >= T_ANKLE:                            # OCCHIELLI (piede/instep)
        L = Pf + B*off + N*0.0015; R = Pf - B*off + N*0.0015
        add_torus(L, N, 0.0040, 0.0014, M_METAL, "Asm_Eyelet")
        add_torus(R, N, 0.0040, 0.0014, M_METAL, "Asm_Eyelet")
        anchors.append((L + N*0.0035, R + N*0.0035))
    else:                                       # SPEED HOOK (gamba)
        L = Pf + B*off + N*0.004; R = Pf - B*off + N*0.004
        add_torus(L, B, 0.0042, 0.0013, M_METAL, "Asm_Hook")
        add_torus(R, B, 0.0042, 0.0013, M_METAL, "Asm_Hook")
        anchors.append((L + N*0.002, R + N*0.002))
# lacci: SOLO incroci a X (+ una traversa in fondo)
add_between(anchors[0][0], anchors[0][1], 0.0028, M_LACE, "Asm_Lace")
for i in range(len(anchors)-1):
    Lc, Rc = anchors[i]; Ln, Rn = anchors[i+1]
    add_between(Lc, Rn, 0.0028, M_LACE, "Asm_Lace")        # incrocio \\
    add_between(Rc, Ln, 0.0028, M_LACE, "Asm_Lace")        # incrocio /
# nodo + due code in cima (fra gli ultimi hook)
kc = (anchors[-1][0] + anchors[-1][1]) * 0.5
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0085, location=kc)
kn = bpy.context.active_object; kn.name = "Asm_Knot"
kn.scale = (1.0, 1.5, 0.7); kn.data.materials.append(M_LACE)
for pp in kn.data.polygons: pp.use_smooth = True
_, Nh, Bh = front_at(T_FRONT_HI)
for sgn in (1, -1):
    tail = kc + Bh*(0.018*sgn) + Nh*0.004 - Vector((0,0,0.030))
    add_between(kc, tail, 0.0026, M_LACE, "Asm_Lace")

det_objs = len([o for o in bpy.data.objects
                if o.name.startswith(("Asm_Eyelet","Asm_Hook","Asm_Lace"))])

# ── LOOK PRODOTTO: pelle nera + rig dark-product (override studio_setup) ────
# pelle dell'upper piu' sottile (5mm -> 2.2mm) per bordi credibili
for mod in up.modifiers:
    if mod.type == 'SOLIDIFY':
        mod.thickness = 0.0022
# luci ritarate per oggetto NERO ~0.27 m (key moderata, rim forte di stacco)
LR = {"K": ( 70, 0.55, (-0.34,-0.30,0.42), (1.00,0.97,0.90)),
      "F": (  6, 1.10, ( 0.36, 0.16,0.20), (0.80,0.88,1.00)),
      "R": (190, 0.10, ( 0.02, 0.40,0.32), (1.00,0.98,0.92))}
for nm,(e,sz,loc,col) in LR.items():
    o = bpy.data.objects.get(nm)
    if o:
        o.data.energy = e; o.data.size = sz; o.data.color = col
        o.location = loc
        d = Vector((0.10,0,0.07)) - Vector(loc)
        o.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
fl = bpy.data.objects.get("KFloor")
if fl:
    fl.location = (0.10, 0, min(0.0, Z_GROUND) - 0.001)
    fb = fl.data.materials[0].node_tree.nodes.get("Principled BSDF")
    fb.inputs["Base Color"].default_value = (0.013,0.013,0.015,1.0)
    fb.inputs["Roughness"].default_value = 0.30
w  = bpy.context.scene.world
wb = w.node_tree.nodes.get("Background")
wb.inputs[0].default_value = (0.010,0.010,0.013,1.0)
wb.inputs[1].default_value = 0.04
sc = bpy.context.scene
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Punchy"
sc.view_settings.exposure = -2.70

gate_ok = (m["components"] == 1 and m["nonmanifold"] == 0)
result = {"validate": m, "GATE_PASS": bool(gate_ok),
          "seams": list(A.seams.keys()),
          "sole_nonmanifold": sole_nonman,
          "sole_verts": len(me_s.vertices),
          "detail_objs": det_objs,
          "bbox_z": [round(min(v.co.z for v in A.mesh.vertices),3),
                     round(max(v.co.z for v in A.mesh.vertices),3)]}
"""


# ── CLAY: materiale uniforme + luce piatta -> la FORMA si legge da ogni lato
# (per definire i punti/struttura mentre si lavora, non il look prodotto).
STRUCT_LOOK = r"""
import bpy
cl = bpy.data.materials.get("ClayStruct") or bpy.data.materials.new("ClayStruct")
cl.use_nodes = True
b = cl.node_tree.nodes.get("Principled BSDF")
b.inputs["Base Color"].default_value = (0.45,0.45,0.47,1.0)
b.inputs["Roughness"].default_value = 0.62
b.inputs["Metallic"].default_value = 0.0
if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value = 0.0
for o in bpy.data.objects:
    if o.type=='MESH' and o.name.startswith("Asm_"):
        o.data.materials.clear(); o.data.materials.append(cl)
        for p in o.data.polygons: p.material_index = 0
# luce quasi-piatta: ogni lato visibile (no dramma, leggibilita')
for nm,e,sz,loc in (("K",55,1.4,(-0.6,-0.7,0.7)),("F",42,1.8,(0.7,0.5,0.4)),
                    ("R",40,1.2,(0.0,0.8,0.7)),("B",30,1.6,(0.2,0.1,-0.6))):
    o=bpy.data.objects.get(nm)
    if o is None:
        bpy.ops.object.light_add(type='AREA', location=loc)
        o=bpy.context.active_object; o.name=nm
    o.data.energy=e; o.data.size=sz; o.data.color=(1,1,1); o.location=loc
    from mathutils import Vector as _V
    d=_V((0.1,0,0.06))-_V(loc); o.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
fl=bpy.data.objects.get("KFloor")
if fl:
    fb=fl.data.materials[0].node_tree.nodes.get("Principled BSDF")
    fb.inputs["Base Color"].default_value=(0.18,0.18,0.20,1.0)
    fb.inputs["Roughness"].default_value=0.8
w=bpy.context.scene.world.node_tree.nodes.get("Background")
w.inputs[0].default_value=(0.20,0.21,0.23,1.0); w.inputs[1].default_value=0.55
sc=bpy.context.scene
sc.view_settings.view_transform="AgX"; sc.view_settings.look="None"
sc.view_settings.exposure=0.0
result={"ok":1}
"""


def _grab(cam_dir, w=900, h=720, samples=48):
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
cam.location=ctr+Vector({tuple(cam_dir)}).normalized()*diag*1.55
d=ctr-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
cam.data.lens=70
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
    r = blender(code, timeout=220)
    return base64.b64decode(r["b64"]) if (r and "b64" in r) else None


def render(path, cam_dir=(0.92, -0.92, 0.42), w=1280, h=900, samples=64):
    png = _grab(cam_dir, w, h, samples)
    if png:
        with open(path, "wb") as f: f.write(png)
        print(f"  render -> {path}")
        return True
    print("  render FALLITO")
    return False


# Foglio multi-vista: 6 angoli compositati in UNA immagine etichettata.
VIEWS = [
    ("front 3/4", ( 0.85,-0.95,0.40)),
    ("toe",       ( 1.00,-0.20,0.16)),
    ("side L",    ( 0.05,-1.00,0.14)),
    ("side R",    ( 0.05, 1.00,0.14)),
    ("heel 3/4",  (-0.85,-0.70,0.42)),
    ("top",       ( 0.10,-0.05,1.00)),
]
def contact_sheet(path, cols=3, cell=(620, 500)):
    from PIL import Image, ImageDraw
    cw, ch = cell
    rows = (len(VIEWS) + cols - 1) // cols
    sheet = Image.new("RGB", (cw*cols, ch*rows), (24, 24, 27))
    dr = ImageDraw.Draw(sheet)
    for i, (label, cd) in enumerate(VIEWS):
        png = _grab(cd, w=cw, h=ch, samples=40)
        if not png:
            print(f"  vista '{label}' FALLITA"); continue
        import io
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if im.size != (cw, ch): im = im.resize((cw, ch))
        x = (i % cols) * cw; y = (i // cols) * ch
        sheet.paste(im, (x, y))
        dr.rectangle([x, y, x+cw-1, y+ch-1], outline=(70, 70, 76))
        dr.text((x+10, y+8), label, fill=(235, 235, 235))
        print(f"  vista '{label}' ok")
    sheet.save(path)
    print(f"  contact-sheet -> {path}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("COMBAT BOOT — upper+gambale via assembly_kernel")
    print("=" * 60)
    r = blender(BUILD, timeout=150)
    if r:
        print("  validate :", r.get("validate"))
        print("  seams    :", r.get("seams"))
        print("  bbox_z   :", r.get("bbox_z"))
        print("  GATE_PASS:", r.get("GATE_PASS"))
        print("  sole_nonman:", r.get("sole_nonmanifold"),
              " sole_verts:", r.get("sole_verts"),
              " detail_objs:", r.get("detail_objs"))
        # 1) hero prodotto (look nero)
        render(f"{RENDER_DIR}/combat_boot_hero.png", cam_dir=(0.85,-0.95,0.40))
        # 2) CLAY: forma leggibile -> foglio multi-vista (vista di lavoro)
        if blender(STRUCT_LOOK, timeout=40):
            contact_sheet(f"{RENDER_DIR}/combat_boot_struct.png")
    print("Done.")
