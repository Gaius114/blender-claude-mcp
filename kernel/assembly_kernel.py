"""
assembly_kernel — kernel di assemblaggio per modellazione a pezzi (Blender 5.x)
==============================================================================
Formalizza la disciplina validata a prototipi (vedi memoria assembly_kernel):

  Autoria LOCALE  + placement RIGIDO (SE3)  + cuciture come ENTITA' CONDIVISE.

Gerarchia dei connettori (tutti validati con metriche oggettive):
  - Frame            : sistema locale rigido (rotazione+traslazione, no scala)
  - parallel_transport: campo di frame anti-drift (curvatura del pezzo)
  - SeamCurve        : connettore 1-D condiviso (bordo di cucitura)
  - JunctionPoint    : connettore 0-D condiviso (dove le cuciture convergono)

Invariante strutturale: un pezzo NON puo' autorare un bordo di cucitura
indipendente. I builder accettano SOLO connettori condivisi per i bordi/
angoli vincolati; l'interno e' libero. Cosi' il fallimento "calzino /
seam-gap / stella lacerata" e' impedito per costruzione, non per disciplina.

Ogni Assembly e' auto-validante: .validate() ritorna le metriche oggettive
(componenti, non-manifold, boundary, gap) usate in tutte le validazioni.

Uso (dentro Blender):
    import sys; sys.path.insert(0, r"D:\\blender-claude\\kernel")
    import assembly_kernel as ak
    import importlib; importlib.reload(ak)
    ak.selftest()
"""

import bpy, bmesh, math
from mathutils import Vector, Matrix, Quaternion

EPS_WELD = 1e-5


# ── Frame: sistema locale RIGIDO (SE3) ───────────────────────────────────────
class Frame:
    __slots__ = ("o", "T", "N", "B")

    def __init__(self, o, T, N):
        T = Vector(T).normalized()
        N = Vector(N)
        N = (N - T * T.dot(N)).normalized()
        B = T.cross(N).normalized()
        N = B.cross(T).normalized()
        self.o = Vector(o)
        self.T, self.N, self.B = T, N, B

    @property
    def M(self):
        return Matrix.Translation(self.o) @ Matrix(
            (self.T, self.N, self.B)).transposed().to_4x4()

    @property
    def Minv(self):
        return self.M.inverted()

    def to_global(self, p):
        return self.M @ Vector(p)

    def to_local(self, p):
        return self.Minv @ Vector(p)

    @staticmethod
    def world():
        return Frame((0, 0, 0), (1, 0, 0), (0, 1, 0))

    @staticmethod
    def from_ring(prev_ring, last_ring):
        """Docking frame: frame rigido alla *fine* di un pezzo (chain)."""
        O = sum(last_ring, Vector()) / len(last_ring)
        Op = sum(prev_ring, Vector()) / len(prev_ring)
        T = (O - Op).normalized()
        B = (last_ring[-1] - last_ring[0]).normalized()
        N = B.cross(T).normalized()
        return Frame(O, T, N)


# ── Campo di frame anti-drift (curvatura del pezzo) ──────────────────────────
def parallel_transport(points, up_hint=Vector((0, 1, 0))):
    n = len(points)
    fr = [None] * n
    T0 = (points[1] - points[0]).normalized()
    up = up_hint if abs(T0.dot(up_hint)) < 0.99 else Vector((1, 0, 0))
    N0 = (up - T0 * T0.dot(up)).normalized()
    fr[0] = (T0, N0, T0.cross(N0).normalized())
    for i in range(1, n):
        Tp, Np, Bp = fr[i - 1]
        if 0 < i < n - 1:
            Tc = (points[i + 1] - points[i - 1]).normalized()
        else:
            Tc = (points[i] - points[i - 1]).normalized()
        ax = Tp.cross(Tc)
        if ax.length > 1e-9:
            ax.normalize()
            ang = math.acos(max(-1.0, min(1.0, Tp.dot(Tc))))
            Nc = Quaternion(ax, ang) @ Np
        else:
            Nc = Np.copy()
        Nc = (Nc - Tc * Tc.dot(Nc)).normalized()
        Bc = Tc.cross(Nc).normalized()
        Nc = Bc.cross(Tc).normalized()
        fr[i] = (Tc, Nc, Bc)
    return fr


# ── Connettori CONDIVISI ─────────────────────────────────────────────────────
class SeamCurve:
    """Connettore 1-D: una sola curva in coordinate globali, posseduta
    dall'assieme. I pezzi adiacenti rigenerano il bordo SU di essa."""
    __slots__ = ("name", "samples", "n")

    def __init__(self, name, samples):
        self.name = name
        self.samples = [Vector(s) for s in samples]
        self.n = len(self.samples)


class JunctionPoint:
    """Connettore 0-D: un solo punto condiviso dove convergono piu' seam."""
    __slots__ = ("name", "p")

    def __init__(self, name, p):
        self.name = name
        self.p = Vector(p)


# ── Assembly: registro connettori + accumulo mesh + validazione ──────────────
class Assembly:
    def __init__(self, name="Asm_Kernel"):
        if not name.startswith("Asm_"):
            name = "Asm_" + name           # convenzione per il bbox-framing
        self.name = name
        self.bm = bmesh.new()
        self.seams = {}
        self.junctions = {}
        self._mat_spans = []               # (face_start, face_end, rgb) -> mosaico
        self._face_count = 0
        self.obj = None
        self.mesh = None

    # -- connettori --
    def seam(self, name, samples):
        sc = SeamCurve(name, samples)
        self.seams[name] = sc
        return sc

    def junction(self, name, p):
        j = JunctionPoint(name, p)
        self.junctions[name] = j
        return j

    # -- emissione griglia (NR x NT) di Vector globali -> quad --
    def _grid(self, pts2d, material=None):
        V = [[self.bm.verts.new(p) for p in row] for row in pts2d]
        f0 = self._face_count
        for i in range(len(V) - 1):
            for k in range(len(V[i]) - 1):
                a, b, c, d = V[i][k], V[i][k + 1], V[i + 1][k + 1], V[i + 1][k]
                # salta quad totalmente degeneri (4 verti coincidenti)
                if (a.co - c.co).length < 1e-12 and (b.co - d.co).length < 1e-12:
                    continue
                try:
                    self.bm.faces.new([a, b, c, d])
                    self._face_count += 1
                except ValueError:
                    pass
        if material is not None:
            self._mat_spans.append((f0, self._face_count, tuple(material)))
        return V

    # -- builder 1: pannello da una superficie master; bordi/angolo VINCOLATI --
    def panel_on_master(self, master_fn, NR, NT, *, edge_t0=None, edge_t1=None,
                         corner=None, material=None):
        """master_fn(r,t)->Vector globale. I bordi t0/t1 e l'angolo (r=0)
        sono SOSTITUITI dai connettori condivisi: il pezzo non puo' decidere
        da solo dove cade la cucitura."""
        pts = []
        for ir in range(NR):
            r = ir / (NR - 1)
            row = []
            for it in range(NT):
                t = it / (NT - 1)
                if ir == 0 and corner is not None:
                    P = corner.p
                elif it == 0 and edge_t0 is not None:
                    P = edge_t0.samples[ir]
                elif it == NT - 1 and edge_t1 is not None:
                    P = edge_t1.samples[ir]
                else:
                    P = master_fn(r, t)
                row.append(Vector(P))
            pts.append(row)
        self._grid(pts, material)
        return pts

    # -- builder 2: pezzo curvo: spine locale + campo di frame; placement rigido --
    def swept_piece(self, frame, spine_local, half_w, NA, *,
                    start_seam=None, end_seam=None, material=None):
        """La curvatura vive SOLO qui (campo di frame anti-drift in locale).
        Placement = frame rigido. start/end ring vincolabili a SeamCurve."""
        FR = parallel_transport([Vector(p) for p in spine_local])
        rings = []
        for p, (T, N, B) in zip(spine_local, FR):
            row = []
            for j in range(NA):
                y = -half_w + 2.0 * half_w * (j / (NA - 1))
                row.append(frame.to_global(Vector(p) + B * y))
            rings.append(row)
        if start_seam is not None:
            rings[0] = [Vector(s) for s in start_seam.samples]
        if end_seam is not None:
            rings[-1] = [Vector(s) for s in end_seam.samples]
        self._grid(rings, material)
        return rings

    # -- finalizza: una sola mesh, salda i vertici condivisi --
    def finalize(self, weld=True):
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        if weld:
            b = bmesh.new()
            b.from_mesh(me)
            bmesh.ops.remove_doubles(b, verts=b.verts, dist=EPS_WELD)
            b.normal_update()
            b.to_mesh(me)
            b.free()
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.collection.objects.link(ob)
        self.obj, self.mesh = ob, me
        self._apply_materials()
        return ob

    def _apply_materials(self):
        if not self._mat_spans:
            return
        me = self.mesh
        mats = {}
        for (_, _, rgb) in self._mat_spans:
            if rgb not in mats:
                m = bpy.data.materials.new(f"{self.name}_{len(mats)}")
                m.use_nodes = True
                bsdf = m.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.42
                mats[rgb] = len(me.materials)
                me.materials.append(m)
        # NB: le facce sono accumulate nell'ordine dei builder; gli span
        # pre-weld restano validi (remove_doubles non riordina le facce).
        for (f0, f1, rgb) in self._mat_spans:
            mi = mats[rgb]
            for fi in range(f0, min(f1, len(me.polygons))):
                me.polygons[fi].material_index = mi
        me.update()

    # -- validazione oggettiva (la prova viaggia col risultato) --
    def validate(self):
        me = self.mesh
        b = bmesh.new()
        b.from_mesh(me)
        nonman = sum(1 for e in b.edges if len(e.link_faces) > 2)
        boundary = sum(1 for e in b.edges if len(e.link_faces) == 1)
        seen = set()
        comp = 0
        for v in b.verts:
            if v.index in seen:
                continue
            comp += 1
            st = [v]
            while st:
                x = st.pop()
                if x.index in seen:
                    continue
                seen.add(x.index)
                for e in x.link_edges:
                    ov = e.other_vert(x)
                    if ov.index not in seen:
                        st.append(ov)
        b.free()
        return {"verts": len(me.vertices), "faces": len(me.polygons),
                "components": comp, "nonmanifold": nonman,
                "boundary_edges": boundary}


# ── Studio preset leggibile (la soluzione strutturale al loop di validazione) ─
def studio_setup(thickness=0.005, exposure=-0.55):
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.startswith("Asm_"):
            if not any(m.type == 'SOLIDIFY' for m in o.modifiers):
                s = o.modifiers.new("Sol", 'SOLIDIFY')
                s.thickness = thickness
                s.offset = 0.0
    for nm, e, sz, loc in (("K", 560, 1.5, (-0.8, -1.1, 1.3)),
                           ("F", 140, 2.6, (1.3, -0.8, 0.7)),
                           ("R", 340, 0.8, (0.25, 1.3, 1.1))):
        if bpy.data.objects.get(nm):
            continue
        bpy.ops.object.light_add(type='AREA', location=loc)
        L = bpy.context.active_object
        L.name = nm
        L.data.energy = e
        L.data.size = sz
        d = Vector((0.1, 0, 0.06)) - Vector(loc)
        L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if not bpy.data.objects.get("KFloor"):
        bpy.ops.mesh.primitive_plane_add(size=4, location=(0.1, 0, -0.01))
        fl = bpy.context.active_object
        fl.name = "KFloor"
        m = bpy.data.materials.new("KFloor")
        m.use_nodes = True
        m.node_tree.nodes.get("Principled BSDF").inputs["Base Color"]\
            .default_value = (0.05, 0.05, 0.06, 1.0)
        fl.data.materials.append(m)
    w = bpy.context.scene.world
    w.use_nodes = True
    wb = w.node_tree.nodes.get("Background")
    wb.inputs[0].default_value = (0.02, 0.02, 0.03, 1.0)
    wb.inputs[1].default_value = 0.07
    sc = bpy.context.scene
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    sc.view_settings.exposure = exposure


# ── SELF-TEST: ricostruisce 2 casi gia' validati VIA LA API FORMALE ──────────
def _clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                bpy.data.cameras, bpy.data.objects, bpy.data.curves):
        for d in list(blk):
            try:
                blk.remove(d)
            except Exception:
                pass


def _case_junction():
    """Giunzione a 3 vie (era junction_proto): 3 pannelli, 3 SeamCurve a
    raggiera, 1 JunctionPoint condiviso. Target: comp=1, nonman=0."""
    R, NR, NT, H, S2 = 0.18, 7, 6, 0.10, 0.060
    PHI = [math.radians(d) for d in (90, 210, 330)]

    def dz(x, y):
        return H * math.exp(-((x * x + y * y) / S2))

    def spoke_pts(k):
        return [Vector((R * r * math.cos(PHI[k]),
                        R * r * math.sin(PHI[k]),
                        dz(R * r * math.cos(PHI[k]), R * r * math.sin(PHI[k]))))
                for r in [i / (NR - 1) for i in range(NR)]]

    A = Assembly("KSelf_Junction")
    JP = A.junction("JP", Vector((0, 0, dz(0, 0))))
    SP = [A.seam(f"S{k}", spoke_pts(k)) for k in range(3)]
    cols = [(0.40, 0.18, 0.12), (0.12, 0.32, 0.42), (0.20, 0.36, 0.16)]
    for k in range(3):
        k2 = (k + 1) % 3
        phi0, phi1 = PHI[k], (PHI[k2] if k < 2 else PHI[0] + 2 * math.pi)

        def master(r, t, phi0=phi0, phi1=phi1):
            phi = phi0 * (1 - t) + phi1 * t
            x = R * r * math.cos(phi)
            y = R * r * math.sin(phi)
            return Vector((x, y, dz(x, y)))

        A.panel_on_master(master, NR, NT,
                          edge_t0=SP[k], edge_t1=SP[k2],
                          corner=JP, material=cols[k])
    A.finalize(weld=True)
    return A


def _case_chain():
    """Catena curva (era compose3d): 2 pezzi curvi via campo di frame,
    docking rigido, bordo iniziale del 2o = SeamCurve = bordo finale del 1o.
    Target: comp=1, nonman=0."""
    K, NA, RB, W = 12, 10, 0.12, 0.13
    BEND = math.radians(90.0)

    def arc_xz():
        return [Vector((RB * math.sin(BEND * i / K), 0.0,
                        RB * (1 - math.cos(BEND * i / K)))) for i in range(K + 1)]

    def arc_xy():
        return [Vector((RB * math.sin(BEND * i / K),
                        RB * (1 - math.cos(BEND * i / K)), 0.0))
                for i in range(K + 1)]

    A = Assembly("KSelf_Chain")
    f1 = Frame.world()
    r1 = A.swept_piece(f1, arc_xz(), W / 2, NA, material=(0.40, 0.20, 0.12))
    s1 = A.seam("chain_s1", r1[-1])                       # bordo finale pezzo1
    f2 = Frame.from_ring(r1[-2], r1[-1])                  # docking rigido
    A.swept_piece(f2, arc_xy(), W / 2, NA,
                  start_seam=s1, material=(0.12, 0.32, 0.42))
    A.finalize(weld=True)
    return A


def selftest():
    _clear()
    aj = _case_junction()
    ac = _case_chain()
    mj = aj.validate()
    mc = ac.validate()
    studio_setup()
    ok_j = (mj["components"] == 1 and mj["nonmanifold"] == 0)
    ok_c = (mc["components"] == 1 and mc["nonmanifold"] == 0)
    return {"junction": mj, "chain": mc,
            "PASS_junction": ok_j, "PASS_chain": ok_c,
            "PASS_ALL": bool(ok_j and ok_c)}
