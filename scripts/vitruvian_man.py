import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# UOMO VITRUVIANO — figura 3D scultorea, posa singola "a stella"
# Costruzione da grafo (motore blender-character ramo A),
# posa canonica BAKED nel grafo: niente rigging.
# Canone: altezza H = apertura braccia (quadrato), ombelico = centro cerchio
# ============================================================

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.worlds):
    for d in list(blk):
        try: blk.remove(d)
        except: pass

H = 1.80                      # altezza totale = lato quadrato
HALF = H/2                    # mezza apertura braccia
Z_NAVEL = 0.605 * H           # ombelico (centro cerchio)
Z_SHLD  = 0.820 * H           # linea spalle (braccia orizzontali)
Z_GROIN = 0.500 * H
Z_KNEE  = 0.285 * H
Z_CHEST = 0.720 * H
Z_NECK  = 0.870 * H
Z_HEADC = H - 0.062*H         # centro testa

def joint(name, pos, r, parent=None):
    return {"name": name, "pos": Vector(pos), "r": r*H, "parent": parent}

# ---- GRAFO IN POSA VITRUVIANA (a stella) ----
g = {}
def J(n, p, rf, par=None): g[n] = joint(n, p, rf, par)
J("root",   (0, 0, Z_GROIN+0.02), 0.066)
J("spine1", (0, 0, (Z_GROIN+Z_CHEST)/2), 0.062, "root")
J("spine2", (0, 0, Z_CHEST), 0.070, "spine1")
J("neck",   (0, 0, Z_NECK),  0.030, "spine2")
J("head",   (0, 0, Z_HEADC+0.05), 0.070, "neck")
for s, sx in (("L", 1), ("R", -1)):
    # BRACCIA ORIZZONTALI: fingertip a x = ±HALF (lati del quadrato)
    J(f"clav{s}",  (sx*0.045*H, 0, Z_SHLD),       0.034, "spine2")
    J(f"upArm{s}", (sx*0.165*H, 0, Z_SHLD+0.004), 0.036, f"clav{s}")
    J(f"loArm{s}", (sx*0.345*H, 0, Z_SHLD),       0.029, f"upArm{s}")
    J(f"hand{s}",  (sx*HALF,    0, Z_SHLD-0.003), 0.027, f"loArm{s}")
    # GAMBE leggermente divaricate
    J(f"hip{s}",   (sx*0.058*H, 0, Z_GROIN-0.02), 0.054, "root")
    J(f"knee{s}",  (sx*0.085*H, 0.006*H, Z_KNEE), 0.044, f"hip{s}")
    J(f"foot{s}",  (sx*0.115*H, 0, 0.022),        0.038, f"knee{s}")
    J(f"toe{s}",   (sx*0.115*H, -0.085*H, 0.012), 0.022, f"foot{s}")

# ---- MOTORE RAMO A (loft anelli + hub) ----
def frame(d):
    d = d.normalized()
    up = Vector((0,0,1)) if abs(d.z) < 0.95 else Vector((1,0,0))
    N = d.cross(up).normalized(); B = d.cross(N).normalized()
    return d, N, B

def ring(bm, c, N, B, rx, ry, seg):
    return [bm.verts.new(c + N*(rx*math.cos(2*math.pi*i/seg))
                           + B*(ry*math.sin(2*math.pi*i/seg)))
            for i in range(seg)]

SEG_PROFILE = {
    "limb":  [(0.0,1.12,1.12),(0.12,0.95,0.95),(0.5,0.85,0.85),
              (0.88,0.95,0.95),(1.0,1.12,1.12)],
    "torso": [(0.0,1.0,0.74),(0.5,1.26,0.86),(1.0,1.05,0.80)],
    "neck":  [(0.0,1.0,1.0),(1.0,0.92,0.92)],
}

def build_mesh(graph, seg=14, name="Vitruviano"):
    bm = bmesh.new()
    for n, j in graph.items():
        if j["parent"] is None: continue
        p = graph[j["parent"]]
        a, b = p["pos"], j["pos"]
        kind = ("torso" if n.startswith(("spine","root"))
                else "neck" if n in ("neck","head") else "limb")
        d, N, B = frame(b - a)
        prev = None
        for (t, sx, sy) in SEG_PROFILE[kind]:
            c = a.lerp(b, t)
            rr = p["r"]*(1-t) + j["r"]*t
            cur = ring(bm, c, N, B, rr*sx, rr*sy, seg)
            if prev:
                for i in range(seg):
                    ni=(i+1)%seg
                    bm.faces.new([prev[i],prev[ni],cur[ni],cur[i]])
            prev = cur
    rmin = min(j["r"] for j in graph.values())
    for n, j in graph.items():
        res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=j["r"]*1.04)
        for v in res["verts"]: v.co = v.co + j["pos"]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=rmin*0.55)
    bm.normal_update()
    me = bpy.data.meshes.new(name+"_m"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    sm = ob.modifiers.new("Sub","SUBSURF"); sm.levels = 3; sm.render_levels = 3
    ob.modifiers.new("Smooth","SMOOTH").iterations = 3
    ob.data.shade_smooth()
    return ob

fig = build_mesh(g, seg=14)

# ---- MATERIALE: gesso/marmo chiaro scultoreo ----
mp = bpy.data.materials.new("Gesso"); mp.use_nodes = True
bp = mp.node_tree.nodes.get("Principled BSDF")
bp.inputs['Base Color'].default_value = (0.80,0.78,0.73,1)
bp.inputs['Roughness'].default_value = 0.62
inp = [i.name for i in bp.inputs]
for s in ('Subsurface Weight','Subsurface'):
    if s in inp: bp.inputs[s].default_value = 0.10; break
if 'Subsurface Radius' in inp:
    bp.inputs['Subsurface Radius'].default_value = (0.18,0.14,0.10)
fig.data.materials.append(mp)

# ---- CERCHIO (centro = ombelico) + QUADRATO (lato = H) ----
R = math.sqrt(HALF**2 + (Z_SHLD - Z_NAVEL)**2)   # passa per i polpastrelli
bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=0.011,
                                 location=(0,0,Z_NAVEL))
circ = bpy.context.active_object; circ.name="Cerchio"
circ.rotation_euler = (math.radians(90),0,0)      # piano XZ (frontale)
circ.data.shade_smooth()

def bar(name, cx,cz, sx,sz):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx,0,cz))
    o=bpy.context.active_object; o.name=name
    o.scale=(sx,0.022,sz); bpy.ops.object.transform_apply(scale=True)
    return o
t=0.020
sq=[bar("Q_bot",0,0, H+t, t), bar("Q_top",0,H, H+t, t),
    bar("Q_L",-HALF,H/2, t,H), bar("Q_R",HALF,H/2, t,H)]
for o in sq: o.select_set(True)
circ.select_set(True)
bpy.context.view_layer.objects.active = sq[0]
bpy.ops.object.join()
geo = bpy.context.active_object; geo.name="Geometria"
md = bpy.data.materials.new("Grafite"); md.use_nodes=True
bd = md.node_tree.nodes.get("Principled BSDF")
bd.inputs['Base Color'].default_value=(0.07,0.065,0.06,1)
bd.inputs['Roughness'].default_value=0.45
bd.inputs['Metallic'].default_value=0.6
geo.data.materials.append(md)

# ---- PAVIMENTO neutro ----
bpy.ops.mesh.primitive_plane_add(size=40, location=(0,0,0))
fl=bpy.context.active_object; fl.name="Floor"
mf=bpy.data.materials.new("Base"); mf.use_nodes=True
mf.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value=(0.21,0.21,0.22,1)
mf.node_tree.nodes.get("Principled BSDF").inputs['Roughness'].default_value=0.7
fl.data.materials.append(mf)

# ---- LUCI studio (frontale, pulito) ----
def area(nm,e,sz,loc,col=(1,1,1)):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L=bpy.context.active_object; L.name=nm
    L.data.energy=e; L.data.size=sz; L.data.color=col
    d=Vector((0,0,Z_NAVEL))-Vector(loc)
    L.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
area("Key", 1100, 2.6, (-2.8,-3.0,3.6), (1.0,0.96,0.90))
area("Fill",170,  6.5, ( 3.0,-2.2,1.8), (0.90,0.94,1.0))
area("Rim", 700,  1.8, ( 0.0, 3.6,3.2), (1.0,0.98,0.95))

world=bpy.data.worlds.new("World"); bpy.context.scene.world=world
world.use_nodes=True
bn=world.node_tree.nodes.get("Background")
bn.inputs[0].default_value=(0.020,0.022,0.028,1); bn.inputs[1].default_value=0.25

# ---- CAMERA frontale ----
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,Z_NAVEL))
tg=bpy.context.active_object; tg.name="T"
bpy.ops.object.camera_add(location=(0.0,-6.4,Z_NAVEL))
cam=bpy.context.active_object; cam.name="Camera"; cam.data.lens=55
tt=cam.constraints.new('TRACK_TO'); tt.target=tg
tt.track_axis='TRACK_NEGATIVE_Z'; tt.up_axis='UP_Y'
bpy.context.scene.camera=cam

sc=bpy.context.scene
try: sc.render.engine="BLENDER_EEVEE_NEXT"
except: sc.render.engine="BLENDER_EEVEE"
if hasattr(sc.eevee,'taa_render_samples'): sc.eevee.taa_render_samples=96
if hasattr(sc.eevee,'use_shadows'): sc.eevee.use_shadows=True
if hasattr(sc.eevee,'use_raytracing'): sc.eevee.use_raytracing=True
sc.render.resolution_x=900; sc.render.resolution_y=1100
sc.render.image_settings.file_format='PNG'
sc.render.use_compositing=False
try:
    sc.view_settings.view_transform="AgX"
    for lk in ("AgX - Base Contrast","AgX - Medium Low Contrast","None"):
        try: sc.view_settings.look=lk; break
        except Exception: continue
except: pass
sc.view_settings.exposure=-0.15
sc.render.filepath="D:/blender-claude/renders/vitruvian_02.png"
bpy.ops.render.render(write_still=True)

result={"saved":sc.render.filepath,"giunti":len(g),
        "verts":len(fig.data.vertices),
        "R_cerchio":round(R,3),"lato_quadrato":H}
