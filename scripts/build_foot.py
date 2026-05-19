import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# build_foot.py — Modulo piede anatomico stilizzato
#
# Tecniche usate:
#   - Parallel Transport lungo la spine curva dell'arco plantare
#   - Profili ellittici asimmetrici (lato mediale ≠ laterale)
#   - 5 dita indipendenti con lunghezze e angoli anatomici
#   - Socket system: restituisce punto di attacco caviglia in coord locali
#
# API:
#   obj, sockets = build_foot(H, side, seg, name)
#   sockets["ankle"] → Vector locale (per attach alla tibia)
# ============================================================


# ---- PARALLEL TRANSPORT ------------------------------------

def _initial_frame(d):
    d = d.normalized()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((0, 1, 0))
    N = d.cross(up).normalized()
    B = d.cross(N).normalized()
    return d, N, B

def _pt_step(prev_d, prev_N, prev_B, new_d):
    new_d = new_d.normalized()
    rot   = prev_d.rotation_difference(new_d)
    return new_d, (rot @ prev_N).normalized(), (rot @ prev_B).normalized()


# ---- RING E BRIDGE -----------------------------------------

def _ring(bm, center, N, B, rx, ry, seg):
    """Anello ellittico con rx lungo N, ry lungo B."""
    return [
        bm.verts.new(
            center
            + N * (rx * math.cos(2 * math.pi * k / seg))
            + B * (ry * math.sin(2 * math.pi * k / seg))
        )
        for k in range(seg)
    ]

def _ring_asym(bm, center, N, B, rx_pos, rx_neg, ry, seg):
    """
    Anello con semi-larghezza diversa sui due lati di N:
    rx_pos = lato N+ (mediale per piede sinistro)
    rx_neg = lato N- (laterale)
    Crea la sezione asimmetrica caratteristica del piede.
    """
    verts = []
    for k in range(seg):
        angle = 2 * math.pi * k / seg
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        rx = rx_pos if cos_a >= 0 else rx_neg
        verts.append(bm.verts.new(
            center + N * (rx * cos_a) + B * (ry * sin_a)
        ))
    return verts

def _bridge(bm, ra, rb):
    seg = len(ra)
    for k in range(seg):
        nk = (k + 1) % seg
        bm.faces.new([ra[k], ra[nk], rb[nk], rb[k]])

def _fan_cap(bm, ring_verts, inward=True):
    """Chiude un ring con triangoli a ventaglio."""
    cx = sum((v.co for v in ring_verts), Vector((0, 0, 0))) / len(ring_verts)
    center = bm.verts.new(cx)
    seg = len(ring_verts)
    for k in range(seg):
        nk = (k + 1) % seg
        if inward:
            bm.faces.new([center, ring_verts[nk], ring_verts[k]])
        else:
            bm.faces.new([center, ring_verts[k], ring_verts[nk]])


# ---- BUILD FOOT --------------------------------------------

def build_foot(H=1.80, side=1, seg=16, name=None):
    """
    Costruisce il piede anatomico stilizzato.

    H:    altezza totale figura (m) — scala tutto
    side: +1 = piede sinistro, -1 = piede destro
    seg:  vertici per anello (16 = buona qualità)
    name: nome oggetto Blender (auto se None)

    Restituisce: (obj, socket_dict)
      socket_dict["ankle"] = Vector in coord locali dell'oggetto
                             (da usare con attach_to() nell'assembly)
    """
    if name is None:
        name = "Foot_L" if side > 0 else "Foot_R"

    # ── Misure anatomiche ─────────────────────────────────────
    FL  = 0.152 * H    # lunghezza piede tacco→punta
    FH  = 0.038 * H    # altezza centro caviglia dal suolo
    ARC = 0.024 * H    # altezza arco plantare (vuoto sotto il mesopiede)

    HW_med = 0.022 * H  # semi-larghezza tacco lato mediale
    HW_lat = 0.020 * H  # semi-larghezza tacco lato laterale
    HH     = 0.028 * H  # semi-altezza tacco

    MW_med = 0.030 * H  # semi-larghezza metatarso lato mediale (alluce)
    MW_lat = 0.024 * H  # semi-larghezza metatarso lato laterale (mignolo)
    MH     = 0.016 * H  # semi-altezza metatarso (piatto)

    # ── Spine (da calcagno a punta) ───────────────────────────
    # Coordinate locali: origin = centro caviglia
    # +Y = avanti (dita), +Z = su, X = mediale (side=+1: X+ = verso mezzanave)
    # Il suolo è a Z = -FH
    #
    # 8 punti chiave con curva che rappresenta l'arco plantare:
    spine_pts = [
        Vector((0, -0.018*H, -FH * 0.95)),   # 0 — prominenza posteriore calcagno
        Vector((0, -0.005*H, -FH)),            # 1 — centro appoggio tacco
        Vector((0,  0.025*H, -FH + ARC*0.4)), # 2 — inizio arco
        Vector((0,  0.058*H, -FH + ARC)),      # 3 — picco arco (piede non tocca)
        Vector((0,  0.090*H, -FH + ARC*0.5)), # 4 — discesa arco
        Vector((0,  0.112*H, -FH)),            # 5 — appoggio avampiede (5° metatarso)
        Vector((0,  0.128*H, -FH)),            # 6 — testa 1° metatarso (alluce)
        Vector((0,  0.148*H, -FH)),            # 7 — base dita
    ]

    # ── Profili per ogni punto spine ─────────────────────────
    # Ogni entry: (rx_med, rx_lat, ry)
    # rx_med = semi-larghezza verso mediale (alluce)
    # rx_lat = semi-larghezza verso laterale (mignolo)
    # ry     = semi-altezza verticale
    prof = [
        (HW_med * 0.90, HW_lat * 0.80, HH * 0.85),   # 0 calcagno post.
        (HW_med,        HW_lat,        HH),             # 1 tacco
        (HW_med * 0.85, HW_lat * 0.80, HH * 0.75),    # 2 arco inizio
        (HW_med * 0.70, HW_lat * 0.65, HH * 0.55),    # 3 arco picco (stretto)
        (MW_med * 0.65, MW_lat * 0.70, HH * 0.55),    # 4 arco fine
        (MW_med * 0.85, MW_lat,        MH * 1.20),     # 5 avampiede lat.
        (MW_med,        MW_lat * 0.80, MH),             # 6 avampiede med.
        (MW_med * 0.85, MW_lat * 0.70, MH * 0.75),    # 7 base dita
    ]

    bm = bmesh.new()

    # ── Loft con Parallel Transport ──────────────────────────
    d, N, B = _initial_frame(spine_pts[1] - spine_pts[0])
    # N punta verso mediale (side * X)
    N = Vector((side, 0, 0))
    B = Vector((0,    0, 1))
    d = (spine_pts[1] - spine_pts[0]).normalized()

    rings = []
    for i, (pt, (rx_m, rx_l, ry)) in enumerate(zip(spine_pts, prof)):
        if i > 0:
            new_d = (spine_pts[i] - spine_pts[i - 1]).normalized()
            d, N, B = _pt_step(d, N, B, new_d)

        # Ring asimmetrico: mediale più largo (alluce) vs laterale (mignolo)
        rx_pos = rx_m  # N+ = mediale
        rx_neg = rx_l  # N- = laterale
        r = _ring_asym(bm, pt, N, B, rx_pos, rx_neg, ry, seg)
        rings.append(r)

    for i in range(len(rings) - 1):
        _bridge(bm, rings[i], rings[i + 1])

    # Cap posteriore (tacco)
    _fan_cap(bm, rings[0], inward=True)

    # ── 5 Dita ───────────────────────────────────────────────
    # Lunghezze (% FL): hallux 22%, 2°24%, 3°22%, 4°18%, 5°15%
    # Angoli (°): alluce più mediale, mignolo più laterale
    # Posizione X base (mediale+): da +MW_med (alluce) a -MW_lat (mignolo)
    toe_data = [
        # (name, x_base_frac, length_frac, angle_deg, r_base, r_tip)
        ("T1", +0.80, 0.220, +12 * side, MW_med * 0.55, MW_med * 0.25),
        ("T2", +0.35, 0.240, + 4 * side, MW_med * 0.38, MW_med * 0.18),
        ("T3", -0.05, 0.220,   0,         MW_med * 0.34, MW_med * 0.16),
        ("T4", -0.42, 0.180, - 5 * side, MW_med * 0.30, MW_med * 0.14),
        ("T5", -0.82, 0.150, -12 * side, MW_med * 0.28, MW_med * 0.13),
    ]

    toe_base_y  = spine_pts[7].y
    toe_base_z  = spine_pts[7].z
    toe_rx_base = (MW_med + MW_lat) * 0.5   # larghezza media alla base dita

    SEG_TOE = max(8, seg // 2)

    for tname, xf, lf, ang_deg, r_base, r_tip in toe_data:
        # Posizione base del dito
        bx = xf * toe_rx_base
        ang = math.radians(ang_deg)
        tl  = lf * FL

        # Direzione dito nel piano XY (con angolo di divergenza)
        td = Vector((math.sin(ang), math.cos(ang), 0)).normalized()
        tN = Vector((math.cos(ang), -math.sin(ang), 0))  # perp in piano XY
        tB = Vector((0, 0, 1))                            # su

        base_pt = Vector((bx, toe_base_y, toe_base_z))
        tip_pt  = base_pt + td * tl

        # 3 anelli per dito: base (più largo), nocca (costrizione), punta
        KNUCKLE = 0.35  # dove si trova l'articolazione metacarpo-falangea
        TOE_SEG = [
            (0.00, r_base),
            (KNUCKLE, r_base * 0.82),  # costrizione al nocca
            (0.55, r_base * 0.78),
            (0.85, r_tip * 1.15),
            (1.00, r_tip),
        ]

        t_rings = []
        for ts, tr in TOE_SEG:
            cp = base_pt.lerp(tip_pt, ts)
            tr_v = _ring(bm, cp, tN, tB, tr * 0.85, tr, SEG_TOE)
            t_rings.append(tr_v)

        for i in range(len(t_rings) - 1):
            _bridge(bm, t_rings[i], t_rings[i + 1])

        # Cap punta dito
        _fan_cap(bm, t_rings[-1], inward=False)

        # Connetti base dito al ring 7 del piede (approssimato con remove_doubles)
        _fan_cap(bm, t_rings[0], inward=True)

    # ── Finalizza mesh ────────────────────────────────────────
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bm.normal_update()
    me = bpy.data.meshes.new(name + "_m")
    bm.to_mesh(me)
    bm.free()

    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    sm = ob.modifiers.new("Sub", "SUBSURF")
    sm.levels = 2
    sm.render_levels = 3
    ob.data.shade_smooth()

    # ── Socket ────────────────────────────────────────────────
    socket_dict = {
        "ankle": Vector((0, 0, 0)),   # origine = centro caviglia
    }

    return ob, socket_dict


# ============================================================
# TEST — render del piede sinistro in vista laterale + 3/4
# ============================================================

if __name__ == "__main__" or True:

    # pulizia
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.materials,
                bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
        for d in list(blk):
            try: blk.remove(d)
            except: pass

    H = 1.80
    foot_L, sockets = build_foot(H=H, side=+1, seg=16, name="Foot_L")

    # materiale: clay skin neutro
    mp = bpy.data.materials.new("Skin_Clay")
    mp.use_nodes = True
    bp = mp.node_tree.nodes.get("Principled BSDF")
    bp.inputs['Base Color'].default_value = (0.76, 0.60, 0.50, 1)
    bp.inputs['Roughness'].default_value  = 0.60
    for s in ('Subsurface Weight', 'Subsurface'):
        if s in [i.name for i in bp.inputs]:
            bp.inputs[s].default_value = 0.12; break
    if 'Subsurface Radius' in [i.name for i in bp.inputs]:
        bp.inputs['Subsurface Radius'].default_value = (0.20, 0.12, 0.08)
    foot_L.data.materials.append(mp)

    # Il piede corre lungo l'asse Y (tacco Y≈-0.03, punta Y≈+0.27)
    # Centro geometrico del piede:
    FH  = 0.038 * H
    FCY = 0.065 * H    # centro Y del piede
    FCZ = -FH * 0.45   # centro Z (leggermente sotto caviglia)
    TGT = Vector((0, FCY, FCZ))

    # pavimento — piano piccolo centrato sul piede
    bpy.ops.mesh.primitive_plane_add(size=0.8, location=(0, FCY, -FH))
    fl = bpy.context.active_object; fl.name = "Floor"
    mf = bpy.data.materials.new("Floor"); mf.use_nodes = True
    mf.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value = (0.12, 0.12, 0.13, 1)
    mf.node_tree.nodes.get("Principled BSDF").inputs['Roughness'].default_value  = 0.82
    fl.data.materials.append(mf)

    # luci calibrate per oggetto ~0.27m — tutte puntate al centro piede
    def area(nm, e, sz, loc, col=(1,1,1)):
        bpy.ops.object.light_add(type='AREA', location=loc)
        L = bpy.context.active_object; L.name = nm
        L.data.energy = e; L.data.size = sz; L.data.color = col
        d = TGT - Vector(loc)
        L.rotation_euler = d.to_track_quat('-Z','Y').to_euler()

    area("Key",  30, 0.22, (-0.20, -0.18, 0.22), (1.00, 0.96, 0.90))
    area("Fill",  5, 0.45, ( 0.18, -0.12, 0.10), (0.88, 0.93, 1.00))
    area("Rim",  16, 0.10, ( 0.02,  0.26, 0.18), (1.00, 0.97, 0.92))
    area("Bot",   2, 0.35, ( 0.00,  FCY, -0.06), (0.90, 0.88, 0.85))

    world = bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs[0].default_value = (0.010, 0.012, 0.016, 1)
    world.node_tree.nodes.get("Background").inputs[1].default_value = 0.05

    # camera 3/4 laterale-frontale, puntata al centro piede
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=TGT)
    tg = bpy.context.active_object; tg.name = "Target"

    bpy.ops.object.camera_add(location=(-0.22, -0.30, 0.18))
    cam = bpy.context.active_object; cam.name = "Camera"
    cam.data.lens = 85
    tt = cam.constraints.new('TRACK_TO')
    tt.target = tg; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'
    bpy.context.scene.camera = cam

    # render
    sc = bpy.context.scene
    try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
    except: sc.render.engine = "BLENDER_EEVEE"
    ev = sc.eevee
    if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 128
    if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
    if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True
    sc.render.resolution_x = 1000
    sc.render.resolution_y = 800
    sc.render.image_settings.file_format = 'PNG'
    sc.render.use_compositing = False
    try:
        sc.view_settings.view_transform = "AgX"
        for lk in ("AgX - Medium Low Contrast", "AgX - Base Contrast", "None"):
            try: sc.view_settings.look = lk; break
            except: pass
    except: pass
    sc.view_settings.exposure = -0.05
    sc.render.filepath = "D:/blender-claude/renders/foot_v1.png"
    bpy.ops.render.render(write_still=True)

    # stats
    vcount = len(foot_L.data.vertices)
    print(f"[foot] verts={vcount}  seg=16  H={H}m  side=L")
    print(f"[foot] ankle_socket={sockets['ankle']}")
    print(f"[foot] saved → {sc.render.filepath}")
