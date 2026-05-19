import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# build_combat_boot.py — Modulo stivale combat militare
#
# Tecniche:
#   - Superellisse (curva di Lamé) per sezione trasversale:
#       n=2 → ellisse, n→∞ → rettangolo
#       n varia lungo la spine: gambale rotondo → punta squadrata
#   - Parallel Transport lungo la spine curva del piede
#   - Tre sotto-moduli: upper + sole + heel_block → join finale
#   - Socket: "ankle" per attacco alla tibia
# ============================================================


# ── PARALLEL TRANSPORT ──────────────────────────────────────

def _pt_step(prev_d, prev_N, prev_B, new_d):
    new_d = new_d.normalized()
    rot   = prev_d.rotation_difference(new_d)
    return new_d, (rot @ prev_N).normalized(), (rot @ prev_B).normalized()


# ── SUPERELLISSE ────────────────────────────────────────────

def _superellipse_ring(bm, center, N, B, rx, ry, n, seg):
    """
    Ring con sezione a superellisse (curva di Lamé).
    |x/rx|^n + |y/ry|^n = 1  →  n=2 ellisse, n=3.5 quasi-rettangolo.

    Parametrizzato con angolo uniforme + proiezione sulla curva:
    x = sign(cos) * |cos|^(2/n) * rx
    y = sign(sin) * |sin|^(2/n) * ry
    """
    verts = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        c, s = math.cos(a), math.sin(a)
        x = math.copysign(abs(c) ** (2.0 / n), c) * rx
        y = math.copysign(abs(s) ** (2.0 / n), s) * ry
        verts.append(bm.verts.new(center + N * x + B * y))
    return verts


def _bridge(bm, ra, rb):
    seg = len(ra)
    for k in range(seg):
        bm.faces.new([ra[k], ra[(k+1)%seg], rb[(k+1)%seg], rb[k]])


def _fan_cap(bm, ring_verts, flip=False):
    cx = sum((v.co for v in ring_verts), Vector()) / len(ring_verts)
    cv = bm.verts.new(cx)
    seg = len(ring_verts)
    for k in range(seg):
        nk = (k + 1) % seg
        if flip:
            bm.faces.new([cv, ring_verts[nk], ring_verts[k]])
        else:
            bm.faces.new([cv, ring_verts[k], ring_verts[nk]])


# ── BUILD UPPER ─────────────────────────────────────────────

def _build_upper(H, side, seg):
    """
    Loft del gambale + tomaia: dalla cima del collare alla punta.
    Restituisce (bm, ring_sole) — ring_sole = ultimo ring in basso
    che servirà per attaccare la suola.
    """
    FL   = 0.152 * H    # lunghezza piede
    FH   = 0.038 * H    # altezza caviglia dal suolo
    COLL = 0.072 * H    # altezza collare sopra caviglia (~13cm totali)
    SL   = 0.014 * H    # spessore suola (sotto la punta del loft)

    # Spine: origin = centro caviglia (0,0,0)
    # +Y avanti, +Z su, +X mediale (side=+1)
    # I punti scendono di FH+SL per raggiungere il piano suola
    SOLE_Z = -(FH + SL)

    spine = [
        Vector((0,  0.000,  COLL)),          # 0 — collare (top socket)
        Vector((0,  0.000,  0.000)),          # 1 — caviglia
        Vector((0, -0.015*H, SOLE_Z*0.60)),  # 2 — tallone posteriore
        Vector((0,  0.020*H, SOLE_Z*0.85)),  # 3 — curva arco
        Vector((0,  0.065*H, SOLE_Z)),       # 4 — piana arco (suola)
        Vector((0,  0.105*H, SOLE_Z)),       # 5 — avampiede
        Vector((0,  0.138*H, SOLE_Z)),       # 6 — base punta
        Vector((0,  0.152*H, SOLE_Z)),       # 7 — punta (cap)
    ]

    # Profili: (rx_med, rx_lat, ry, n_superellisse)
    # rx_med = semi-larghezza verso mediale
    # rx_lat = semi-larghezza verso laterale
    # ry     = semi-altezza
    # n      = esponente Lamé (2=ellisse, 3.5=quasi-rettangolo)
    prof = [
        (0.048*H, 0.044*H, 0.040*H, 2.2),   # 0 collare — rotondo, aperto
        (0.040*H, 0.037*H, 0.034*H, 2.5),   # 1 caviglia
        (0.036*H, 0.033*H, 0.030*H, 2.8),   # 2 tallone
        (0.038*H, 0.034*H, 0.026*H, 3.0),   # 3 arco (schiacciato)
        (0.042*H, 0.038*H, 0.024*H, 3.2),   # 4 piana
        (0.046*H, 0.042*H, 0.024*H, 3.4),   # 5 avampiede (più largo)
        (0.044*H, 0.040*H, 0.022*H, 3.5),   # 6 base punta (squadrata)
        (0.036*H, 0.033*H, 0.020*H, 3.5),   # 7 punta (piccola e squadrata)
    ]

    bm = bmesh.new()

    # Frame iniziale: N verso mediale, B verso alto
    N = Vector((side, 0, 0))
    B = Vector((0, 0, 1))
    d = (spine[1] - spine[0]).normalized()

    rings = []
    for i, (pt, (rx_m, rx_l, ry, n)) in enumerate(zip(spine, prof)):
        if i > 0:
            nd = (spine[i] - spine[i-1]).normalized()
            d, N, B = _pt_step(d, N, B, nd)

        # Larghezza asimmetrica: mediale (N+) vs laterale (N-)
        # Usiamo un ring misto: campionatura angolare che sceglie rx
        verts = []
        for k in range(seg):
            a   = 2 * math.pi * k / seg
            c   = math.cos(a)
            s   = math.sin(a)
            rx  = rx_m if c >= 0 else rx_l    # mediale vs laterale
            x   = math.copysign(abs(c) ** (2.0 / n), c) * rx
            y   = math.copysign(abs(s) ** (2.0 / n), s) * ry
            verts.append(bm.verts.new(pt + N * x + B * y))
        rings.append(verts)

    # Bridge tra ring consecutivi
    for i in range(len(rings) - 1):
        _bridge(bm, rings[i], rings[i+1])

    # Cap collare in alto (ring 0)
    _fan_cap(bm, rings[0], flip=True)

    # Cap punta (ring 7) — non chiudiamo il basso: sarà saldato alla suola
    _fan_cap(bm, rings[-1], flip=False)

    return bm, rings[-2]   # ring -2 = base punta (da usare per sole boundary)


# ── BUILD SOLE ──────────────────────────────────────────────

def _build_sole(H, side, seg_sole=32):
    """
    Suola: profilo a boot-print estruso verso il basso.
    Welt (bordo sporgente ~4mm) + spessore suola 14mm.
    """
    FL   = 0.152 * H
    FH   = 0.038 * H
    SL   = 0.014 * H    # spessore suola
    SOLE_Z = -(FH + SL)
    WELT = 0.004 * H    # sporgenza welt
    top_z = SOLE_Z
    bot_z = SOLE_Z - SL

    # Profilo 2D del bootprint in piano XY (Y = avanti, X = lato)
    # Lista di punti che tracciano il contorno del fondo stivale
    # (metà sinistra, poi simmetrica a destra)
    # Coordinate normalizzate a FL: scalate in build

    def bootprint(n_pts=seg_sole):
        """
        Genera il contorno oval-rettangolare del bootprint.
        Asse principale lungo Y, leggermente più largo sul lato mediale.
        """
        pts = []
        for k in range(n_pts):
            a = 2 * math.pi * k / n_pts
            c, s = math.cos(a), math.sin(a)
            # Superellisse allungata (n=2.5 lungo Y, n=3.0 lungo X)
            rx = (0.052*H + WELT) * (1.0 + 0.08 * side * c)  # asimm. mediale
            ry_f = 0.088 * H + WELT   # semi-lunghezza avanti
            ry_b = 0.068 * H + WELT   # semi-lunghezza indietro (tacco)
            ry   = ry_f if s >= 0 else ry_b
            x = math.copysign(abs(c) ** (2.0/3.0), c) * rx
            y = math.copysign(abs(s) ** (2.0/2.5), s) * ry
            # Offset: centro spostato leggermente avanti rispetto all'origine
            pts.append(Vector((x, y + 0.018*H, top_z)))
        return pts

    bm = bmesh.new()
    top_pts = bootprint()
    top_verts = [bm.verts.new(p) for p in top_pts]
    bot_verts = [bm.verts.new(Vector((p.x, p.y, bot_z))) for p in top_pts]

    n = len(top_verts)
    # Pareti laterali (welt)
    for k in range(n):
        bm.faces.new([top_verts[k], top_verts[(k+1)%n],
                      bot_verts[(k+1)%n], bot_verts[k]])
    # Piano superiore suola
    bm.faces.new(top_verts[::-1])
    # Piano inferiore suola
    bm.faces.new(bot_verts)

    return bm


# ── BUILD HEEL BLOCK ────────────────────────────────────────

def _build_heel(H):
    """
    Tacco: blocco rettangolare smussato, staccato dalla suola principale.
    Altezza 3cm, footprint ~7x5cm, bordi smussati.
    """
    FH   = 0.038 * H
    SL   = 0.014 * H
    HL   = 0.030 * H    # altezza tacco
    HRX  = 0.034 * H    # semi-larghezza X
    HRY  = 0.025 * H    # semi-profondità Y
    BEVEL= 0.005 * H    # raggio smussatura
    N_SEG = 6           # segmenti per quarto di cerchio al bevel

    # Centro tacco: leggermente dietro l'origine (tallone)
    CY   = -0.022 * H
    top_z = -(FH + SL)
    bot_z = top_z - HL

    bm = bmesh.new()

    def heel_ring(z, shrink=0.0):
        """Ring superellittico per il tacco (n=4, quasi-rettangolo)."""
        rx = HRX - shrink
        ry = HRY - shrink
        n  = 4.0
        seg = 24
        return [bm.verts.new(Vector((
            math.copysign(abs(math.cos(2*math.pi*k/seg))**(2/n), math.cos(2*math.pi*k/seg)) * rx,
            CY + math.copysign(abs(math.sin(2*math.pi*k/seg))**(2/n), math.sin(2*math.pi*k/seg)) * ry,
            z
        ))) for k in range(seg)]

    top_ring = heel_ring(top_z, shrink=BEVEL*0.5)
    bot_ring = heel_ring(bot_z, shrink=0)

    _bridge(bm, top_ring, bot_ring)
    _fan_cap(bm, top_ring, flip=True)
    _fan_cap(bm, bot_ring, flip=False)

    return bm


# ── BUILD COMBAT BOOT (assembly) ────────────────────────────

def build_combat_boot(H=1.80, side=1, seg=20, name=None):
    """
    Costruisce lo stivale combat completo.

    H:    altezza figura (m)
    side: +1 = sinistro, -1 = destro
    seg:  vertici per anello del gambale
    name: nome oggetto Blender

    Restituisce: (obj, socket_dict)
      socket_dict["ankle"] = Vector locale (≈ origin)
    """
    if name is None:
        name = "Boot_L" if side > 0 else "Boot_R"

    # Costruisci i tre sotto-moduli in bmesh e unisci
    bm_upper, _ = _build_upper(H, side, seg)
    bm_sole     = _build_sole(H, side)
    bm_heel     = _build_heel(H)

    bm_final = bmesh.new()
    for bm_src in (bm_upper, bm_sole, bm_heel):
        # Salva riferimento diretto al mesh temporaneo (non usare [-1])
        tmp_me = bpy.data.meshes.new("_boot_tmp")
        bm_src.to_mesh(tmp_me)
        bm_final.from_mesh(tmp_me)
        bpy.data.meshes.remove(tmp_me)
        bm_src.free()

    bmesh.ops.remove_doubles(bm_final, verts=bm_final.verts, dist=0.0008)
    bm_final.normal_update()

    me = bpy.data.meshes.new(name + "_m")
    bm_final.to_mesh(me)
    bm_final.free()

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

    socket_dict = {"ankle": Vector((0, 0, 0))}
    return ob, socket_dict


# ============================================================
# TEST — render stivale combat sinistro, vista 3/4
# ============================================================

if __name__ == "__main__" or True:

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.materials,
                bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
        for d in list(blk):
            try: blk.remove(d)
            except: pass

    H = 1.80
    boot, sockets = build_combat_boot(H=H, side=+1, seg=20, name="Boot_L")

    # materiale: cuoio nero opaco
    mp = bpy.data.materials.new("Leather_Black")
    mp.use_nodes = True
    nt = mp.node_tree
    bp = nt.nodes.get("Principled BSDF")
    bp.inputs['Base Color'].default_value = (0.022, 0.019, 0.016, 1)
    bp.inputs['Roughness'].default_value  = 0.75
    if 'Specular IOR Level' in [i.name for i in bp.inputs]:
        bp.inputs['Specular IOR Level'].default_value = 0.30
    # bump grana cuoio
    noi = nt.nodes.new('ShaderNodeTexNoise'); noi.location = (-400, -200)
    noi.inputs['Scale'].default_value    = 200.0
    noi.inputs['Detail'].default_value   = 8.0
    noi.inputs['Roughness'].default_value = 0.65
    bmp = nt.nodes.new('ShaderNodeBump'); bmp.location = (-160, -200)
    bmp.inputs['Strength'].default_value  = 0.20
    bmp.inputs['Distance'].default_value  = 0.002
    nt.links.new(noi.outputs['Fac'],    bmp.inputs['Height'])
    nt.links.new(bmp.outputs['Normal'], bp.inputs['Normal'])
    # Assegnazione materiale robusta per Blender 5.x
    if boot.data.materials:
        boot.data.materials[0] = mp
    else:
        boot.data.materials.append(mp)
    bpy.context.view_layer.objects.active = boot
    boot.active_material = mp

    # suola: gomma scura
    ms = bpy.data.materials.new("Rubber_Sole")
    ms.use_nodes = True
    ns = ms.node_tree; ns.nodes.clear()
    os2 = ns.nodes.new('ShaderNodeOutputMaterial')
    bs  = ns.nodes.new('ShaderNodeBsdfPrincipled')
    bs.inputs['Base Color'].default_value = (0.018, 0.016, 0.014, 1)
    bs.inputs['Roughness'].default_value  = 0.92
    ns.links.new(bs.outputs['BSDF'], os2.inputs['Surface'])
    # non applicato qui: in un pipeline completo si usa UV island per separare suola

    # pavimento
    FH  = 0.038 * H
    SL  = 0.014 * H
    FCY = 0.065 * H
    FCZ = -(FH + SL) * 0.5
    GND = -(FH + SL + 0.014*H)

    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, FCY, GND))
    fl = bpy.context.active_object; fl.name = "Floor"
    mf = bpy.data.materials.new("Floor"); mf.use_nodes = True
    mf.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value = (0.10, 0.10, 0.11, 1)
    mf.node_tree.nodes.get("Principled BSDF").inputs['Roughness'].default_value  = 0.85
    fl.data.materials.append(mf)

    # luci — calibrate per oggetto ~0.25m
    TGT = Vector((0, FCY, FCZ))
    def area(nm, e, sz, loc, col=(1,1,1)):
        bpy.ops.object.light_add(type='AREA', location=loc)
        L = bpy.context.active_object; L.name = nm
        L.data.energy = e; L.data.size = sz; L.data.color = col
        d = TGT - Vector(loc)
        L.rotation_euler = d.to_track_quat('-Z','Y').to_euler()

    area("Key",  18, 0.28, (-0.24, -0.22, 0.26), (1.00, 0.96, 0.90))
    area("Fill",  3, 0.55, ( 0.22, -0.14, 0.12), (0.88, 0.93, 1.00))
    area("Rim",  10, 0.12, ( 0.04,  0.30, 0.20), (1.00, 0.97, 0.92))
    area("Bot",   1, 0.40, ( 0.00,  FCY,  GND + 0.05), (0.85, 0.83, 0.80))

    world = bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs[0].default_value = (0.008, 0.009, 0.012, 1)
    world.node_tree.nodes.get("Background").inputs[1].default_value = 0.04

    # camera 3/4
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=TGT)
    tg = bpy.context.active_object; tg.name = "Target"
    bpy.ops.object.camera_add(location=(-0.28, -0.52, 0.22))
    cam = bpy.context.active_object; cam.name = "Camera"; cam.data.lens = 80
    tt = cam.constraints.new('TRACK_TO')
    tt.target = tg; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'
    bpy.context.scene.camera = cam

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
    sc.view_settings.exposure = 0.8
    sc.render.filepath = "D:/blender-claude/renders/combat_boot_v1.png"
    bpy.ops.render.render(write_still=True)
    print(f"[boot] verts={len(boot.data.vertices)}  saved→{sc.render.filepath}")
