import bpy, bmesh, math, random
from mathutils import Vector, Quaternion
import mathutils.noise as mnoise

# ============================================================
# ULIVO MEDITERRANEO — tronco contorto + chioma a ciuffi
# ============================================================
random.seed(11)

# ---- CLEAR SCENE ----
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.curves):
    for d in list(blk):
        blk.remove(d)

def nvec(p, scale, seed):
    q = p * scale
    return Vector((mnoise.noise(q + Vector((seed, 0, 0))),
                   mnoise.noise(q + Vector((0, seed, 0))),
                   mnoise.noise(q + Vector((0, 0, seed))))).normalized()

# ---- RAMIFICAZIONE RICORSIVA ----
branches = []   # ognuno: (points[list Vector], radii[list float], depth)
tips = []       # (pos, depth) -> per la chioma

def grow(start, direction, length, r0, r1, depth, seed):
    n = max(6, int(length / 0.11))
    pts = [start.copy()]
    d = direction.normalized()
    pos = start.copy()
    for i in range(1, n + 1):
        t = i / n
        # twist organico via noise (forte sul tronco -> nodoso/contorto)
        g = nvec(pos, 1.1 + depth * 0.35, seed)
        # leggera tendenza verso l'alto per i limbi, droop solo sui rametti
        up_bias = Vector((0, 0, 1)) * max(0.0, 0.30 - depth * 0.05)
        droop = Vector((0, 0, -1)) * (0.45 * t * t) if depth >= 4 else Vector()
        W = 0.26 + depth * 0.05
        d = ((1 - W) * d + W * g + up_bias + droop).normalized()
        pos = pos + d * (length / n)
        pts.append(pos.copy())
    radii = [r0 + (r1 - r0) * (i / n) for i in range(n + 1)]
    branches.append((pts, radii, depth))
    end = pts[-1]
    end_dir = (pts[-1] - pts[-2]).normalized()

    if depth >= MAX_DEPTH:
        tips.append((end, depth))
        return
    if depth >= 3:
        tips.append((end, depth))

    if depth == 0:   nch = 3
    elif depth <= 2: nch = random.choice([2, 3, 3])
    else:            nch = 2
    rc = r1 * (1.0 / nch) ** (1.0 / 2.3)
    rc = max(rc, 0.012)
    for k in range(nch):
        perp = end_dir.cross(Vector((random.uniform(-1, 1),
                                     random.uniform(-1, 1),
                                     random.uniform(-1, 1)))).normalized()
        ang = math.radians(random.uniform(28, 55))
        cdir = (Quaternion(perp, ang) @ end_dir).normalized()
        # apertura: i limbi bassi si allargano, i rami salgono
        spread = Vector((cdir.x, cdir.y, 0)).normalized() * (0.30 if depth <= 1 else 0.0)
        cdir = (cdir + Vector((0, 0, 0.30)) * max(0.0, 0.5 - depth * 0.08)
                + spread).normalized()
        clen = length * random.uniform(0.72, 0.90)
        grow(end, cdir, clen, rc, rc * random.uniform(0.5, 0.65),
             depth + 1, seed + 7 * (k + 1))

MAX_DEPTH = 5
# tronco corto, MOLTO grosso e contorto
grow(Vector((0, 0, 0)), Vector((0.06, 0.04, 1)).normalized(),
     1.5, 0.40, 0.28, 0, 1.0)

# ---- LOFT RAMI in un unico bmesh ----
def pt_frames(points):
    n = len(points)
    fr = [None] * n
    T0 = (points[1] - points[0]).normalized()
    up = Vector((0, 0, 1))
    if abs(T0.dot(up)) > 0.99: up = Vector((1, 0, 0))
    N0 = T0.cross(up).normalized()
    fr[0] = (T0, N0, T0.cross(N0).normalized())
    for i in range(1, n):
        Tp, Np, Bp = fr[i - 1]
        Tc = (points[i] - points[i - 1]).normalized() if i == n - 1 \
            else (points[i + 1] - points[i - 1]).normalized()
        ax = Tp.cross(Tc)
        if ax.length > 1e-8:
            ax.normalize()
            ca = max(-1, min(1, Tp.dot(Tc)))
            Nc = Quaternion(ax, math.acos(ca)) @ Np
        else:
            Nc = Np.copy()
        Nc = (Nc - Tc * Tc.dot(Nc)).normalized()
        Bc = Tc.cross(Nc).normalized()
        Nc = Bc.cross(Tc).normalized()
        fr[i] = (Tc, Nc, Bc)
    return fr

SEGB = 7
tb = bmesh.new()
for pts, radii, depth in branches:
    if len(pts) < 2:
        continue
    fr = pt_frames(pts)
    rings = []
    for p, (T, N, B), r in zip(pts, fr, radii):
        ring = [tb.verts.new(p + N * (r * math.cos(2 * math.pi * j / SEGB))
                               + B * (r * math.sin(2 * math.pi * j / SEGB)))
                for j in range(SEGB)]
        rings.append(ring)
    for ri in range(len(rings) - 1):
        a, b = rings[ri], rings[ri + 1]
        for j in range(SEGB):
            nj = (j + 1) % SEGB
            tb.faces.new([a[j], a[nj], b[nj], b[j]])
tb.normal_update()
bmesh.ops.recalc_face_normals(tb, faces=tb.faces)
tm = bpy.data.meshes.new("Tronco_mesh")
tb.to_mesh(tm); tb.free()
tronco = bpy.data.objects.new("Tronco_Rami", tm)
bpy.context.collection.objects.link(tronco)
tronco.data.shade_smooth()

# ---- CHIOMA: tanti ciuffi piccoli e frastagliati, solo sulle punte ----
# usa SOLO i tip esterni (depth >= 3): cosi' i rami restano visibili
outer = [(p, dp) for (p, dp) in tips if dp >= 3]
random.shuffle(outer)

cb = bmesh.new()
n_clusters = 0
for (pos, depth) in outer:
    nsub = random.choice([1, 1, 2, 2, 3])
    base_r = random.uniform(0.13, 0.27) * (1.15 if depth >= 5 else 0.9)
    for s in range(nsub):
        c = pos + Vector((random.uniform(-0.16, 0.16),
                          random.uniform(-0.16, 0.16),
                          random.uniform(-0.08, 0.14)))
        r = base_r * random.uniform(0.6, 1.0)
        tmp = bmesh.new()
        bmesh.ops.create_icosphere(tmp, subdivisions=2, radius=r)
        sx = random.uniform(1.0, 1.7)
        sy = random.uniform(0.65, 1.05)
        sz = random.uniform(0.70, 1.10)
        for v in tmp.verts:
            v.co.x *= sx; v.co.y *= sy; v.co.z *= sz
            dirn = v.co.normalized()
            # displacement forte e a piu' ottave -> frastagliato, non bolla
            nv = (mnoise.noise(v.co * 3.0 + Vector((s * 4, depth, 0))) * 0.45
                  + mnoise.noise(v.co * 7.0) * 0.28
                  + mnoise.noise(v.co * 15.0) * 0.14)
            v.co += dirn * (r * nv)
            v.co += c
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces)
        vmap = {v: cb.verts.new(v.co) for v in tmp.verts}
        cb.verts.ensure_lookup_table()
        for f in tmp.faces:
            try:
                cb.faces.new([vmap[v] for v in f.verts])
            except ValueError:
                pass
        tmp.free()
        n_clusters += 1

cb.normal_update()
cm = bpy.data.meshes.new("Chioma_mesh")
cb.to_mesh(cm); cb.free()
chioma = bpy.data.objects.new("Chioma", cm)
bpy.context.collection.objects.link(chioma)
chioma.data.shade_smooth()
# niente SubSurf: deve restare frastagliata, non liscia

# ---- MINI-FOGLIE instanziate sui ciuffi frontali/superiori ----
cm.calc_loop_triangles()
front_faces = []
for poly in cm.polygons:
    nx, ny, nz = poly.normal
    # solo facce verso camera (-Y) o verso il cielo (top) -> "frontali"
    if ny < 0.12 or nz > 0.38:
        front_faces.append((Vector(poly.center), Vector(poly.normal)))

random.shuffle(front_faces)
# copertura PIENA: piu' foglie per faccia (modello pesante, voluto)
LEAVES_PER_FACE = 3

lb = bmesh.new()
n_leaves = 0
for (c, nrm) in front_faces:
    n = nrm.normalized()
    up = Vector((0, 0, 1))
    if abs(n.dot(up)) > 0.95:
        up = Vector((1, 0, 0))
    t0 = n.cross(up).normalized()
    b0 = n.cross(t0).normalized()
    for _ in range(LEAVES_PER_FACE):
        # sparpaglia attorno al centro faccia nel piano tangente
        jr = random.uniform(0.0, 0.055)
        ja = random.uniform(0, 2 * math.pi)
        cc = c + (math.cos(ja) * t0 + math.sin(ja) * b0) * jr
        a = random.uniform(0, 2 * math.pi)
        Ldir = (math.cos(a) * t0 + math.sin(a) * b0)
        Ldir = (Ldir + Vector((0, 0, -0.45))).normalized()   # droop
        Wax = n.cross(Ldir).normalized()
        L = random.uniform(0.060, 0.105)
        W = L * random.uniform(0.17, 0.23)
        curl = L * random.uniform(0.10, 0.22)
        off = n * random.uniform(0.004, 0.018)
        base = cc + off
        tip  = cc + off + Ldir * L
        lft  = cc + off + Ldir * (0.42 * L) + Wax * W + n * curl
        rgt  = cc + off + Ldir * (0.42 * L) - Wax * W + n * curl
        vb = lb.verts.new(base)
        vt = lb.verts.new(tip)
        vl = lb.verts.new(lft)
        vr = lb.verts.new(rgt)
        lb.faces.new([vb, vl, vt])
        lb.faces.new([vb, vt, vr])
        n_leaves += 1

lb.normal_update()
lm = bpy.data.meshes.new("Foglie_mesh")
lb.to_mesh(lm); lb.free()
foglie = bpy.data.objects.new("Foglie", lm)
bpy.context.collection.objects.link(foglie)
foglie.data.shade_smooth()

# ---- MATERIALE CORTECCIA ----
def bark_mat():
    m = bpy.data.materials.new("Corteccia_Olivo")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o  = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (700, 0)
    b  = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (340, 0)
    b.inputs['Roughness'].default_value = 0.82
    # colore variabile
    n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location = (-360, 60)
    n1.inputs['Scale'].default_value = 12.0
    n1.inputs['Detail'].default_value = 6.0
    cr = nt.nodes.new('ShaderNodeValToRGB'); cr.location = (-120, 60)
    cr.color_ramp.elements[0].color = (0.085, 0.072, 0.055, 1)
    cr.color_ramp.elements[1].color = (0.20, 0.19, 0.16, 1)
    nt.links.new(n1.outputs['Fac'], cr.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
    # bump fessure: due scale
    n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location = (-360, -240)
    n2.inputs['Scale'].default_value = 12.0
    n2.inputs['Detail'].default_value = 8.0
    n3 = nt.nodes.new('ShaderNodeTexNoise'); n3.location = (-360, -460)
    n3.inputs['Scale'].default_value = 60.0
    bmp1 = nt.nodes.new('ShaderNodeBump'); bmp1.location = (-120, -260)
    bmp1.inputs['Strength'].default_value = 0.45
    bmp1.inputs['Distance'].default_value = 0.02
    bmp2 = nt.nodes.new('ShaderNodeBump'); bmp2.location = (120, -300)
    bmp2.inputs['Strength'].default_value = 0.18
    bmp2.inputs['Distance'].default_value = 0.006
    nt.links.new(n2.outputs['Fac'], bmp1.inputs['Height'])
    nt.links.new(bmp1.outputs['Normal'], bmp2.inputs['Normal'])
    nt.links.new(n3.outputs['Fac'], bmp2.inputs['Height'])
    nt.links.new(bmp2.outputs['Normal'], b.inputs['Normal'])
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m

# ---- MATERIALE FOGLIAME ----
def foliage_mat():
    m = bpy.data.materials.new("Fogliame_Olivo")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o  = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (760, 0)
    b  = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (380, 0)
    inp = [i.name for i in b.inputs]
    b.inputs['Roughness'].default_value = 0.60
    for s in ('Subsurface Weight', 'Subsurface'):
        if s in inp: b.inputs[s].default_value = 0.14; break
    if 'Subsurface Radius' in inp:
        b.inputs['Subsurface Radius'].default_value = (0.09, 0.20, 0.05)
    # fattore: noise fine -> ramp con verde DOMINANTE, argento solo in coda
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.location = (-520, 60)
    nz.inputs['Scale'].default_value = 130.0
    nz.inputs['Detail'].default_value = 8.0
    nz.inputs['Roughness'].default_value = 0.75
    cr = nt.nodes.new('ShaderNodeValToRGB'); cr.location = (-260, 40)
    ramp = cr.color_ramp
    ramp.elements.new(0.55)
    ramp.elements.new(0.86)
    # assegna i colori per posizione (robusto al ri-ordinamento)
    palette = [
        (0.00, (0.022, 0.045, 0.014, 1.0)),  # verde molto scuro (interno in ombra)
        (0.55, (0.055, 0.085, 0.040, 1.0)),  # verde scuro
        (0.86, (0.105, 0.135, 0.085, 1.0)),  # verde medio
        (1.00, (0.20, 0.23, 0.18, 1.0)),     # salvia (poco)
    ]
    for el in ramp.elements:
        nearest = min(palette, key=lambda pc: abs(pc[0] - el.position))
        el.color = nearest[1]
    nt.links.new(nz.outputs['Fac'], cr.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
    # bump fine micro-rottura
    nb = nt.nodes.new('ShaderNodeTexNoise'); nb.location = (-420, -300)
    nb.inputs['Scale'].default_value = 70.0
    nb.inputs['Detail'].default_value = 7.0
    bmp = nt.nodes.new('ShaderNodeBump'); bmp.location = (-200, -260)
    bmp.inputs['Strength'].default_value = 0.55
    bmp.inputs['Distance'].default_value = 0.010
    nb2 = nt.nodes.new('ShaderNodeTexNoise'); nb2.location = (-420, -520)
    nb2.inputs['Scale'].default_value = 230.0
    nb2.inputs['Detail'].default_value = 4.0
    bmp2 = nt.nodes.new('ShaderNodeBump'); bmp2.location = (0, -300)
    bmp2.inputs['Strength'].default_value = 0.30
    bmp2.inputs['Distance'].default_value = 0.003
    nt.links.new(nb.outputs['Fac'], bmp.inputs['Height'])
    nt.links.new(bmp.outputs['Normal'], bmp2.inputs['Normal'])
    nt.links.new(nb2.outputs['Fac'], bmp2.inputs['Height'])
    nt.links.new(bmp2.outputs['Normal'], b.inputs['Normal'])
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m

def leaf_mat():
    m = bpy.data.materials.new("Foglia_Olivo")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o  = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (760, 0)
    b  = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (420, 0)
    inp = [i.name for i in b.inputs]
    b.inputs['Roughness'].default_value = 0.58
    for s in ('Subsurface Weight', 'Subsurface'):
        if s in inp: b.inputs[s].default_value = 0.16; break
    if 'Subsurface Radius' in inp:
        b.inputs['Subsurface Radius'].default_value = (0.10, 0.22, 0.06)
    # verde sopra, ARGENTO sotto (Backfacing) — firma dell'olivo al vento
    geo = nt.nodes.new('ShaderNodeNewGeometry'); geo.location = (-260, -120)
    nz  = nt.nodes.new('ShaderNodeTexNoise');    nz.location = (-460, 120)
    nz.inputs['Scale'].default_value = 38.0
    nz.inputs['Detail'].default_value = 4.0
    cr  = nt.nodes.new('ShaderNodeValToRGB');    cr.location = (-240, 140)
    cr.color_ramp.elements[0].color = (0.042, 0.082, 0.026, 1.0)  # verde scuro
    cr.color_ramp.elements[1].color = (0.115, 0.150, 0.078, 1.0)  # verde medio
    nt.links.new(nz.outputs['Fac'], cr.inputs['Fac'])
    # backfacing attenuato -> sotto-foglia salvia (non bianco acceso)
    bfac = nt.nodes.new('ShaderNodeMath'); bfac.location = (-40, -120)
    bfac.operation = 'MULTIPLY'
    bfac.inputs[1].default_value = 0.6
    nt.links.new(geo.outputs['Backfacing'], bfac.inputs[0])
    backmix = nt.nodes.new('ShaderNodeMix'); backmix.location = (220, 0)
    backmix.data_type = 'RGBA'; backmix.blend_type = 'MIX'
    backmix.inputs[7].default_value = (0.255, 0.290, 0.225, 1.0)   # argento-salvia sotto
    nt.links.new(cr.outputs['Color'], backmix.inputs[6])
    nt.links.new(bfac.outputs[0], backmix.inputs[0])
    nt.links.new(backmix.outputs[2], b.inputs['Base Color'])
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    m.use_backface_culling = False
    return m

BARK = bark_mat()
FOL  = foliage_mat()
LEAF = leaf_mat()
tronco.data.materials.append(BARK)
chioma.data.materials.append(FOL)
foglie.data.materials.append(LEAF)

# ---- TERRENO ----
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0.0))
ground = bpy.context.active_object
ground.name = "Terreno"
gm = bpy.data.materials.new("Terra_Secca")
gm.use_nodes = True
gnt = gm.node_tree; gnt.nodes.clear()
go = gnt.nodes.new('ShaderNodeOutputMaterial'); go.location = (400, 0)
gb = gnt.nodes.new('ShaderNodeBsdfPrincipled'); gb.location = (140, 0)
gb.inputs['Roughness'].default_value = 0.9
gnz = gnt.nodes.new('ShaderNodeTexNoise'); gnz.location = (-300, 0)
gnz.inputs['Scale'].default_value = 8.0
gcr = gnt.nodes.new('ShaderNodeValToRGB'); gcr.location = (-80, 0)
gcr.color_ramp.elements[0].color = (0.16, 0.14, 0.09, 1)
gcr.color_ramp.elements[1].color = (0.22, 0.19, 0.13, 1)
gnt.links.new(gnz.outputs['Fac'], gcr.inputs['Fac'])
gnt.links.new(gcr.outputs['Color'], gb.inputs['Base Color'])
gnt.links.new(gb.outputs['BSDF'], go.inputs['Surface'])
ground.data.materials.append(gm)

# ---- ERBA: ciuffi di fili secchi mediterranei ----
def wind_at(p):
    v = nvec(Vector((p.x, p.y, 0.0)), 0.25, 13.0)
    base = Vector((0.55, 0.25, 0.0))            # direzione vento dominante
    return (base + Vector((v.x, v.y, 0.0)) * 0.6)

gb = bmesh.new()
n_grass = 0
N_TUFTS = 2600
for _ in range(N_TUFTS):
    # area inquadrata, piu' densa in primo piano (y verso camera = negativo)
    cx = random.uniform(-9.0, 9.0)
    cy = random.uniform(-9.5, 5.0)
    d_tree = math.hypot(cx, cy)
    if d_tree < 0.7:                 # radura attorno al tronco
        continue
    # bias densita': scarta piu' spesso lo sfondo
    fg = 1.0 - max(0.0, (cy + 9.5) / 14.5) * 0.55
    if random.random() > (0.55 + 0.45 * fg):
        continue
    nblades = random.randint(5, 12)
    for _b in range(nblades):
        ang = random.uniform(0, 2 * math.pi)
        rr = random.uniform(0.0, 0.16)
        bx = cx + math.cos(ang) * rr
        by = cy + math.sin(ang) * rr
        base = Vector((bx, by, 0.0))
        h = random.uniform(0.13, 0.42) * (0.8 + 0.4 * fg)
        w = random.uniform(0.006, 0.011)
        face_a = random.uniform(0, 2 * math.pi)
        t = Vector((math.cos(face_a), math.sin(face_a), 0.0))
        wax = Vector((-t.y, t.x, 0.0))           # asse larghezza
        lean = wind_at(base) * (h * random.uniform(0.35, 0.7))
        P0 = base
        P1 = base + Vector((0, 0, h * 0.55)) + lean * 0.35
        P2 = base + Vector((0, 0, h)) + lean
        bl = gb.verts.new(P0 + wax * w)
        br = gb.verts.new(P0 - wax * w)
        ml = gb.verts.new(P1 + wax * w * 0.6)
        mr = gb.verts.new(P1 - wax * w * 0.6)
        tp = gb.verts.new(P2)
        gb.faces.new([bl, br, mr, ml])
        gb.faces.new([ml, mr, tp])
        n_grass += 1

gb.normal_update()
grm = bpy.data.meshes.new("Erba_mesh")
gb.to_mesh(grm); gb.free()
erba = bpy.data.objects.new("Erba", grm)
bpy.context.collection.objects.link(erba)
erba.data.shade_smooth()

# materiale erba secca (paglia <-> verde secco, due facce)
em = bpy.data.materials.new("Erba_Secca")
em.use_nodes = True
ent = em.node_tree; ent.nodes.clear()
eo = ent.nodes.new('ShaderNodeOutputMaterial'); eo.location = (560, 0)
eb = ent.nodes.new('ShaderNodeBsdfPrincipled'); eb.location = (240, 0)
einp = [i.name for i in eb.inputs]
eb.inputs['Roughness'].default_value = 0.85
for s in ('Subsurface Weight', 'Subsurface'):
    if s in einp: eb.inputs[s].default_value = 0.10; break
if 'Subsurface Radius' in einp:
    eb.inputs['Subsurface Radius'].default_value = (0.25, 0.20, 0.06)
enz = ent.nodes.new('ShaderNodeTexNoise'); enz.location = (-360, 40)
enz.inputs['Scale'].default_value = 6.0
enz.inputs['Detail'].default_value = 5.0
ecr = ent.nodes.new('ShaderNodeValToRGB'); ecr.location = (-120, 40)
ecr.color_ramp.elements[0].color = (0.135, 0.105, 0.045, 1.0)  # paglia/terra
ecr.color_ramp.elements[1].color = (0.205, 0.215, 0.095, 1.0)  # verde secco
ent.links.new(enz.outputs['Fac'], ecr.inputs['Fac'])
ent.links.new(ecr.outputs['Color'], eb.inputs['Base Color'])
ent.links.new(eb.outputs['BSDF'], eo.inputs['Surface'])
em.use_backface_culling = False
erba.data.materials.append(em)

# ---- LUCI ----
bpy.ops.object.light_add(type='SUN', location=(6, -6, 12))
sun = bpy.context.active_object
sun.name = "Sole"
sun.data.energy = 5.0
sun.data.color = (1.0, 0.93, 0.78)
sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.radians(50), 0, math.radians(35))

bpy.ops.object.light_add(type='AREA', location=(-5, 6, 7))
fill = bpy.context.active_object
fill.name = "Cielo_Fill"
fill.data.energy = 180
fill.data.size = 12
fill.data.color = (0.55, 0.70, 1.0)
d = Vector((0, 0, 2.2)) - Vector((-5, 6, 7))
fill.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

# ---- WORLD (cielo tenue) ----
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.07, 0.11, 0.17, 1.0)
bg.inputs[1].default_value = 0.75

# ---- CAMERA (3/4 dal basso) ----
zmax = max(v.co.z for v in chioma.data.vertices)
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, 0.0, zmax * 0.55))
tgt = bpy.context.active_object; tgt.name = "CamTarget"
bpy.ops.object.camera_add(location=(9.5, -12.5, 2.0))
cam = bpy.context.active_object; cam.name = "Camera"
cam.data.lens = 52
tt = cam.constraints.new('TRACK_TO')
tt.target = tgt; tt.track_axis = 'TRACK_NEGATIVE_Z'; tt.up_axis = 'UP_Y'
bpy.context.scene.camera = cam

# ---- RENDER ----
sc = bpy.context.scene
try:    sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
ev = sc.eevee
if hasattr(ev, 'taa_render_samples'): ev.taa_render_samples = 96
if hasattr(ev, 'use_shadows'):        ev.use_shadows = True
if hasattr(ev, 'use_raytracing'):     ev.use_raytracing = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.render.filepath = "D:/blender-claude/renders/olive_09_grass.png"
sc.render.image_settings.file_format = 'PNG'
sc.render.use_compositing = False
try:
    sc.view_settings.view_transform = "AgX"
    for lk in ("AgX - Base Contrast", "AgX - Medium Low Contrast",
               "AgX - Base", "None"):
        try:
            sc.view_settings.look = lk
            break
        except Exception:
            continue
except: pass
sc.view_settings.exposure = 0.0
bpy.ops.render.render(write_still=True)

result = {"saved": sc.render.filepath,
          "branches": len(branches),
          "clusters": n_clusters,
          "leaves": n_leaves,
          "grass_blades": n_grass,
          "tronco_verts": len(tronco.data.vertices),
          "chioma_verts": len(chioma.data.vertices),
          "foglie_verts": len(foglie.data.vertices),
          "erba_verts": len(erba.data.vertices)}
