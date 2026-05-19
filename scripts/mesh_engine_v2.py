import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# MESH ENGINE v2 — motore mesh bipede migliorato
#
# Miglioramenti rispetto al motore originale (vitruvian/guardian):
#   1. Parallel Transport tra segmenti contigui (no torsione ai giunti)
#   2. Support loops vicino ai capi di ogni segmento (SubSurf controllato)
#   3. Hub radius derivato dalla scala endpoint del profilo (no grumi)
#   4. remove_doubles threshold basato sul passo angolare locale (no buchi)
# ============================================================

# ---- SEG_PROFILE v2 ----------------------------------------
# Ogni entry: (t_lungo_segmento, scala_x, scala_y)
# Support loop a ~8% e ~92%: concentrano edge loops dove SubSurf
# deve tenere la forma dell'articolazione senza collassare o gonfiarsi.
SEG_PROFILE = {
    "limb": [
        (0.00, 1.12, 1.12),   # hub A
        (0.08, 1.00, 1.00),   # support A  ← nuovo
        (0.22, 0.90, 0.90),   # taper
        (0.50, 0.84, 0.84),   # mid (stretto)
        (0.78, 0.90, 0.90),   # taper
        (0.92, 1.00, 1.00),   # support B  ← nuovo
        (1.00, 1.12, 1.12),   # hub B
    ],
    "torso": [
        (0.00, 1.00, 0.74),
        (0.10, 1.06, 0.77),   # support A
        (0.50, 1.28, 0.86),
        (0.90, 1.08, 0.79),   # support B
        (1.00, 1.05, 0.78),
    ],
    "neck": [
        (0.00, 1.00, 1.00),
        (0.35, 0.96, 0.96),
        (1.00, 0.90, 0.90),
    ],
}

# Scala dell'endpoint limb: usata per dimensionare hub icosphere
_LIMB_EP = SEG_PROFILE["limb"][0][1]   # 1.12


# ---- FRAME UTILITIES ---------------------------------------

def _initial_frame(d):
    """TNB frame iniziale da direzione d (Gram-Schmidt)."""
    d = d.normalized()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
    N = d.cross(up).normalized()
    B = d.cross(N).normalized()
    return d, N, B


def _pt_step(prev_d, prev_N, prev_B, new_d):
    """Parallel Transport: ruota il frame precedente del minimo necessario
    per allinearsi alla nuova direzione new_d.
    Evita la torsione accumulata che si vede ai giunti dopo SubSurf."""
    new_d = new_d.normalized()
    rot = prev_d.rotation_difference(new_d)
    N = (rot @ prev_N).normalized()
    B = (rot @ prev_B).normalized()
    return new_d, N, B


def ring(bm, center, N, B, rx, ry, seg):
    """Anello ellittico di vertici attorno a center."""
    return [
        bm.verts.new(
            center
            + N * (rx * math.cos(2 * math.pi * i / seg))
            + B * (ry * math.sin(2 * math.pi * i / seg))
        )
        for i in range(seg)
    ]


# ---- TOPOLOGICAL SORT -------------------------------------

def _topo_order(graph):
    """Restituisce i nodi in ordine padre-prima (DFS su radici)."""
    order, visited = [], set()
    def dfs(n):
        if n in visited: return
        j = graph[n]
        if j["parent"]: dfs(j["parent"])
        visited.add(n)
        order.append(n)
    for n in graph: dfs(n)
    return order


# ---- BUILD MESH -------------------------------------------

def build_biped_mesh(graph, seg=14, name="Character"):
    """
    Costruisce la mesh bipede da un grafo di giunti.

    graph: dict {name: {"pos": Vector, "r": float, "parent": str|None}}
    seg:   numero di vertici per anello (suggerito: 12–16)
    name:  nome oggetto Blender

    Restituisce l'oggetto Blender con SubSurf (levels=2) e shade_smooth.
    """
    bm = bmesh.new()

    # frames[n] = (d, N, B) in uscita dal nodo n
    frames = {}

    for n in _topo_order(graph):
        j = graph[n]

        # --- nodo radice: frame iniziale verso il primo figlio
        if j["parent"] is None:
            children = [c for c, cj in graph.items() if cj["parent"] == n]
            d0 = (graph[children[0]]["pos"] - j["pos"]) if children else Vector((0, 0, 1))
            frames[n] = _initial_frame(d0)
            continue

        p   = graph[j["parent"]]
        a, b = p["pos"], j["pos"]
        seg_d = (b - a)
        if seg_d.length < 1e-6:
            frames[n] = frames[j["parent"]]
            continue

        # Parallel Transport dal frame del padre al nuovo segmento
        prev_d, prev_N, prev_B = frames[j["parent"]]
        d, N, B = _pt_step(prev_d, prev_N, prev_B, seg_d)
        frames[n] = (d, N, B)

        kind = (
            "torso" if n.startswith(("spine", "root"))
            else "neck" if n in ("neck", "head")
            else "limb"
        )
        prof = SEG_PROFILE[kind]

        prev_r = None
        for (t, sx, sy) in prof:
            c  = a.lerp(b, t)
            rr = p["r"] * (1 - t) + j["r"] * t
            cur = ring(bm, c, N, B, rr * sx, rr * sy, seg)
            if prev_r:
                for i in range(seg):
                    ni = (i + 1) % seg
                    bm.faces.new([prev_r[i], prev_r[ni], cur[ni], cur[i]])
            prev_r = cur

    # --- Hub ai giunti
    # hub_scale = 0.88: hub leggermente DENTRO il ring endpoint (1.12*r).
    # Così SubSurf arrotonda il giunto senza creare grumi.
    # Per ogni coppia di giunti fratelli (stesso parent), il raggio viene
    # ulteriormente ridotto se i due hub si sovrapporrebbero.
    hub_scale_base = 0.88
    for n, j in graph.items():
        r_hub = j["r"] * hub_scale_base
        # Clamp: non superare metà distanza dal giunto fratello più vicino
        siblings = [cj for cn, cj in graph.items()
                    if cn != n and cj["parent"] == j["parent"] and j["parent"] is not None]
        for sib in siblings:
            half_dist = (j["pos"] - sib["pos"]).length * 0.44
            r_hub = min(r_hub, half_dist)
        r_hub = max(r_hub, j["r"] * 0.50)  # minimo 50% del raggio giunto
        res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r_hub)
        for v in res["verts"]:
            v.co = v.co + j["pos"]

    # --- remove_doubles con soglia basata sul passo angolare mediano
    # Passo angolare = 2π*r/seg ≈ distanza tra vertici adiacenti sull'anello.
    # Threshold = 28% di quel passo: abbastanza grande da fondere
    # hub+ring coincidenti, abbastanza piccola da non toccare ring adiacenti.
    sorted_r = sorted(j["r"] for j in graph.values())
    median_r  = sorted_r[len(sorted_r) // 2]
    merge_dist = median_r * 2 * math.pi / seg * 0.28
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)

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

    return ob


# ============================================================
# TEST — eseguibile direttamente in Blender
# Costruisce un bipede in A-pose con il motore v2
# e renderizza in D:/blender-claude/renders/mesh_engine_v2_test.png
# ============================================================

if __name__ == "__main__" or True:

    # --- pulizia scena
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.materials,
                bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
        for d in list(blk):
            try: blk.remove(d)
            except: pass

    # --- grafo bipede (A-pose, 1.80 m, proporzioni 7.6 teste)
    def joint(name, pos, r, parent=None):
        return {"name": name, "pos": Vector(pos), "r": r, "parent": parent}

    H  = 1.80
    HU = H / 7.6
    RB = H

    g = {}
    def J(n, p, rf, par=None): g[n] = joint(n, p, rf * RB, par)

    # Posizioni basate su H (non HU) per garantire clearance sufficiente
    # tra hub fratelli (hip/knee/foot/shoulder).
    # Proporzioni vitruviane adattate ad A-pose (braccia a ~45° in basso).
    Z_GROIN = 0.500 * H
    Z_CHEST = 0.720 * H
    Z_SHLD  = 0.820 * H
    Z_NECK  = 0.870 * H
    Z_KNEE  = 0.285 * H

    J("root",   (0, 0, Z_GROIN),           0.068)
    J("spine1", (0, 0, (Z_GROIN+Z_CHEST)/2), 0.064, "root")
    J("spine2", (0, 0, Z_CHEST),           0.072, "spine1")
    J("neck",   (0, 0, Z_NECK),            0.030, "spine2")
    J("head",   (0, 0, H - 0.062*H),       0.072, "neck")

    for s, sx in (("L", 1), ("R", -1)):
        # Spalle: x = 0.110*H garantisce clearance fra i due clavicle hub
        # Braccia in A-pose: angolo ~40° verso il basso dall'orizzontale
        J(f"clav{s}",  (sx*0.110*H, 0, Z_SHLD),           0.032, "spine2")
        J(f"upArm{s}", (sx*0.210*H, 0, Z_SHLD - 0.080*H), 0.030, f"clav{s}")
        J(f"loArm{s}", (sx*0.290*H, 0, Z_SHLD - 0.165*H), 0.025, f"upArm{s}")
        J(f"hand{s}",  (sx*0.360*H, 0, Z_SHLD - 0.240*H), 0.027, f"loArm{s}")
        # Gambe: x = 0.058*H (vitruvian) → hub non si sovrappongono
        J(f"hip{s}",   (sx*0.058*H,  0,         Z_GROIN - 0.020*H), 0.052, "root")
        J(f"knee{s}",  (sx*0.064*H,  0.004*H,   Z_KNEE),            0.040, f"hip{s}")
        J(f"foot{s}",  (sx*0.068*H,  0,         0.022*H),           0.034, f"knee{s}")
        J(f"toe{s}",   (sx*0.068*H, -0.067*H,   0.010*H),           0.022, f"foot{s}")

    # --- build mesh v2
    fig = build_biped_mesh(g, seg=14, name="BipedV2")

    # --- materiale: clay neutro con SSS leggero
    mp = bpy.data.materials.new("Clay")
    mp.use_nodes = True
    bp = mp.node_tree.nodes.get("Principled BSDF")
    bp.inputs['Base Color'].default_value = (0.72, 0.65, 0.58, 1)
    bp.inputs['Roughness'].default_value  = 0.65
    for s in ('Subsurface Weight', 'Subsurface'):
        if s in [i.name for i in bp.inputs]:
            bp.inputs[s].default_value = 0.08; break
    fig.data.materials.append(mp)

    # --- luci studio
    Z_MID = H * 0.55
    def area(nm, e, sz, loc, col=(1, 1, 1)):
        bpy.ops.object.light_add(type='AREA', location=loc)
        L = bpy.context.active_object; L.name = nm
        L.data.energy = e; L.data.size = sz; L.data.color = col
        d = Vector((0, 0, Z_MID)) - Vector(loc)
        L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    area("Key",  1200, 2.4, (-2.6, -3.0, 3.4), (1.0, 0.96, 0.90))
    area("Fill",  180, 6.0, ( 3.0, -2.0, 1.8), (0.90, 0.94, 1.0))
    area("Rim",   600, 1.6, ( 0.0,  3.4, 3.2), (1.0, 0.98, 0.96))

    world = bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes.get("Background").inputs[0].default_value = (0.018, 0.020, 0.026, 1)
    world.node_tree.nodes.get("Background").inputs[1].default_value = 0.22

    # --- pavimento
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    fl = bpy.context.active_object; fl.name = "Floor"
    mf = bpy.data.materials.new("Base"); mf.use_nodes = True
    mf.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value = (0.20, 0.20, 0.21, 1)
    mf.node_tree.nodes.get("Principled BSDF").inputs['Roughness'].default_value  = 0.72
    fl.data.materials.append(mf)

    # --- camera frontale 3/4 alta
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, Z_MID))
    tg = bpy.context.active_object; tg.name = "Target"
    bpy.ops.object.camera_add(location=(0.6, -3.8, Z_MID + 0.1))
    cam = bpy.context.active_object; cam.name = "Camera"; cam.data.lens = 75
    tt = cam.constraints.new('TRACK_TO')
    tt.target = tg; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'
    bpy.context.scene.camera = cam

    # --- render
    sc = bpy.context.scene
    try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
    except: sc.render.engine = "BLENDER_EEVEE"
    ev = sc.eevee
    if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 96
    if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
    if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True
    sc.render.resolution_x = 900
    sc.render.resolution_y = 1100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.use_compositing = False
    try:
        sc.view_settings.view_transform = "AgX"
        for lk in ("AgX - Base Contrast", "AgX - Medium Low Contrast", "None"):
            try: sc.view_settings.look = lk; break
            except: pass
    except: pass
    sc.view_settings.exposure = -0.10
    sc.render.filepath = "D:/blender-claude/renders/mesh_engine_v2_test.png"
    bpy.ops.render.render(write_still=True)

    print({
        "saved":    sc.render.filepath,
        "verts":    len(fig.data.vertices),
        "joints":   len(g),
        "seg":      14,
        "profiles": {k: len(v) for k, v in SEG_PROFILE.items()},
        "merge_dist_mm": round(
            sorted(j["r"] for j in g.values())[len(g)//2]
            * 2 * math.pi / 14 * 0.28 * 1000, 2
        ),
    })
