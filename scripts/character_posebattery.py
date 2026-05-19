import bpy, bmesh, math
from mathutils import Vector

# ============================================================
# VALIDAZIONE blender-character (rig-centrico) — POSE BATTERY
# Costruisce 1 personaggio + rig, lo prova in 4 pose diverse.
# ============================================================

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.armatures, bpy.data.worlds):
    for d in list(blk):
        try: blk.remove(d)
        except: pass

# ---- ENGINE (dalla skill, ramo A) ----
def joint(name, pos, radius, parent=None):
    return {"name": name, "pos": Vector(pos), "r": radius, "parent": parent}

def biped_graph(total_h=1.80, heads=7.5, build=1.0):
    HU = total_h / heads
    RB = total_h
    g = {}
    def J(n, p, rf, par=None): g[n] = joint(n, p, rf*RB*build, par)
    J("root",   (0, 0, 3.4*HU), 0.068)
    J("spine1", (0, 0, 4.2*HU), 0.064, "root")
    J("spine2", (0, 0, 5.0*HU), 0.072, "spine1")
    J("neck",   (0, 0, 5.8*HU), 0.030, "spine2")
    J("head",   (0, -0.03*HU, 6.4*HU), 0.072, "neck")
    for s, sx in (("L", 1), ("R", -1)):
        J(f"clav{s}",  (sx*0.16*HU, 0,       5.62*HU), 0.032, "spine2")
        J(f"upArm{s}", (sx*0.42*HU, 0.02*HU, 4.95*HU), 0.030, f"clav{s}")
        J(f"loArm{s}", (sx*0.55*HU, 0.04*HU, 4.25*HU), 0.025, f"upArm{s}")
        J(f"hand{s}",  (sx*0.60*HU, 0.05*HU, 3.80*HU), 0.028, f"loArm{s}")
        J(f"hip{s}",   (sx*0.12*HU, 0, 3.35*HU), 0.052, "root")
        J(f"knee{s}",  (sx*0.13*HU, 0.012*HU, 1.9*HU), 0.038, f"hip{s}")
        J(f"foot{s}",  (sx*0.13*HU, 0, 0.15*HU), 0.034, f"knee{s}")
        J(f"toe{s}",   (sx*0.13*HU, -0.13*HU, 0.04*HU), 0.022, f"foot{s}")
    return g, HU

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
    "limb":  [(0.0,1.15,1.15),(0.12,0.95,0.95),(0.5,0.85,0.85),
              (0.88,0.95,0.95),(1.0,1.15,1.15)],
    "torso": [(0.0,1.0,0.72),(0.5,1.28,0.86),(1.0,1.05,0.78)],
    "neck":  [(0.0,1.0,1.0),(1.0,0.92,0.92)],
}

def build_biped_mesh(graph, seg=12, name="Personaggio"):
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
                    ni = (i+1) % seg
                    bm.faces.new([prev[i], prev[ni], cur[ni], cur[i]])
            prev = cur
    rmin = min(j["r"] for j in graph.values())
    for n, j in graph.items():
        res = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=j["r"]*1.16)
        for v in res["verts"]:
            v.co = v.co + j["pos"]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=rmin*0.35)
    bm.normal_update()
    me = bpy.data.meshes.new(name+"_m"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.modifiers.new("Sub","SUBSURF").levels = 2
    ob.data.shade_smooth()
    return ob

def build_armature(graph, mesh_obj, name="Rig", roll_ref=(0,1,0)):
    arm = bpy.data.armatures.new(name); rig = bpy.data.objects.new(name, arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    bones = {}
    for n, j in graph.items():
        if j["parent"] is None: continue
        b = arm.edit_bones.new(n)
        b.head = graph[j["parent"]]["pos"]; b.tail = j["pos"]
        bones[n] = b
    for n, b in bones.items():
        pj = graph[n]["parent"]
        if pj and pj in bones: b.parent = bones[pj]
    rr = Vector(roll_ref)
    for b in arm.edit_bones:
        b.align_roll(rr)
    bpy.ops.object.mode_set(mode='OBJECT')
    segs = [(n, graph[j["parent"]]["pos"], j["pos"])
            for n, j in graph.items() if j["parent"]]
    vg = {n: mesh_obj.vertex_groups.new(name=n) for n,_,_ in segs}
    def d_seg(p, a, b):
        ab = b - a; L2 = ab.length_squared or 1e-9
        t = max(0.0, min(1.0, (p - a).dot(ab) / L2))
        return (p - (a + ab*t)).length
    for v in mesh_obj.data.vertices:
        p = v.co
        ds = sorted(((d_seg(p,a,b)+1e-5, n) for n,a,b in segs))[:3]
        ws = [(n, 1.0/(d**4)) for d,n in ds]
        s = sum(w for _,w in ws)
        for n,w in ws:
            vg[n].add([v.index], w/s, 'REPLACE')
    am = mesh_obj.modifiers.new("Armature","ARMATURE"); am.object = rig
    mesh_obj.parent = rig
    cs = mesh_obj.modifiers.new("CorrSmooth","CORRECTIVE_SMOOTH")
    cs.factor = 0.6; cs.iterations = 12
    return rig

def apply_pose(rig, pose):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.rotation_mode = 'XYZ'; pb.rotation_euler = (0,0,0)
    for bn,(rx,ry,rz) in pose.items():
        pb = rig.pose.bones.get(bn)
        if pb: pb.rotation_euler = (math.radians(rx),math.radians(ry),
                                    math.radians(rz))
    bpy.ops.object.mode_set(mode='OBJECT')

POSE_BATTERY = {
    "rest":   {},
    "arms_up":{"upArmL":(0,0,95),"upArmR":(0,0,-95),
               "loArmL":(20,0,0),"loArmR":(20,0,0)},
    "sit":    {"hipL":(-90,0,0),"hipR":(-90,0,0),
               "kneeL":(95,0,0),"kneeR":(95,0,0),"spine1":(10,0,0)},
    "crouch": {"hipL":(-70,0,0),"hipR":(-70,0,0),
               "kneeL":(110,0,0),"kneeR":(110,0,0),
               "spine1":(25,0,0),"spine2":(15,0,0),
               "upArmL":(35,0,0),"upArmR":(35,0,0)},
}

# ---- COSTRUZIONE ----
G, HU = biped_graph(total_h=1.80, heads=7.6)
char = build_biped_mesh(G, seg=12, name="Personaggio")
rig  = build_armature(G, char, name="Rig")

mat = bpy.data.materials.new("Skin")
mat.use_nodes = True
b = mat.node_tree.nodes.get("Principled BSDF")
b.inputs['Base Color'].default_value = (0.45,0.34,0.30,1)
b.inputs['Roughness'].default_value = 0.55
char.data.materials.append(mat)

# ---- SCENA NEUTRA ----
bpy.ops.mesh.primitive_plane_add(size=30, location=(0,0,0))
gr = bpy.context.active_object; gr.name = "Ground"
gm = bpy.data.materials.new("Grey"); gm.use_nodes = True
gm.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value=(0.18,0.18,0.19,1)
gr.data.materials.append(gm)

def area(nm, e, sz, loc, col=(1,1,1)):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.active_object; L.name = nm
    L.data.energy=e; L.data.size=sz; L.data.color=col
    d = Vector((0,0,1.0)) - Vector(loc)
    L.rotation_euler = d.to_track_quat('-Z','Y').to_euler()
area("Key", 600, 3.0, (-3,-3,4), (1.0,0.97,0.92))
area("Fill",180, 5.0, ( 4,-2,2), (0.9,0.94,1.0))
area("Rim", 400, 1.5, ( 0, 4,3), (1.0,0.98,0.95))

world = bpy.data.worlds.new("World"); bpy.context.scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes.get("Background")
bgn.inputs[0].default_value=(0.05,0.055,0.065,1); bgn.inputs[1].default_value=0.5

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0.95))
tgt = bpy.context.active_object; tgt.name="T"
bpy.ops.object.camera_add(location=(0.0,-5.0,1.05))
cam = bpy.context.active_object; cam.name="Camera"; cam.data.lens=50
tt=cam.constraints.new('TRACK_TO'); tt.target=tgt
tt.track_axis='TRACK_NEGATIVE_Z'; tt.up_axis='UP_Y'
bpy.context.scene.camera=cam

sc = bpy.context.scene
try: sc.render.engine="BLENDER_EEVEE_NEXT"
except: sc.render.engine="BLENDER_EEVEE"
if hasattr(sc.eevee,'taa_render_samples'): sc.eevee.taa_render_samples=64
if hasattr(sc.eevee,'use_shadows'): sc.eevee.use_shadows=True
sc.render.resolution_x=720; sc.render.resolution_y=1280
sc.render.image_settings.file_format='PNG'
sc.render.use_compositing=False
try:
    sc.view_settings.view_transform="AgX"
    for lk in ("AgX - Base Contrast","AgX - Medium Low Contrast","None"):
        try: sc.view_settings.look=lk; break
        except Exception: continue
except: pass

# ---- POSE BATTERY: un render per posa ----
done = []
for name, pose in POSE_BATTERY.items():
    apply_pose(rig, pose)
    bpy.context.view_layer.update()
    sc.render.filepath = f"D:/blender-claude/renders/char_{name}.png"
    bpy.ops.render.render(write_still=True)
    done.append(name)

result = {"poses": done, "giunti": len(G),
          "verts": len(char.data.vertices)}
