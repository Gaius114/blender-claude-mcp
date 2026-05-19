import bpy, bmesh, math
from mathutils import Vector, Quaternion

# ============================================================
# NUMERIA — Guardiano (skill blender-character, RAMO A)
# Base parametrica autorata: loft ad anelli + hub ai giunti
# Inserito nella scena del risveglio (_04, approvata)
# ============================================================

# ---- CLEAR ----
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
            bpy.data.cameras, bpy.data.armatures, bpy.data.worlds,
            bpy.data.metaballs):
    for d in list(blk):
        try: blk.remove(d)
        except: pass

# ---- ENGINE: GRAFO DI GIUNTI ----
def joint(name, pos, radius, parent=None):
    return {"name": name, "pos": Vector(pos), "r": radius, "parent": parent}

def biped_graph(total_h=1.80, heads=7.5, build=1.0):
    HU = total_h / heads     # POSIZIONI in teste
    RB = total_h             # RAGGI = frazione dell'altezza (mai *HU)
    g = {}
    def J(n, p, rf, par=None): g[n] = joint(n, p, rf*RB*build, par)
    J("root",   (0, 0, 3.4*HU), 0.068)
    J("spine1", (0, 0, 4.2*HU), 0.064, "root")
    J("spine2", (0, 0, 5.0*HU), 0.072, "spine1")
    J("neck",   (0, 0, 5.8*HU), 0.030, "spine2")
    J("head",   (0, -0.03*HU, 6.4*HU), 0.072, "neck")
    for s, sx in (("L", 1), ("R", -1)):
        J(f"clav{s}",  (sx*0.18*HU, 0, 5.65*HU), 0.032, "spine2")
        J(f"upArm{s}", (sx*0.55*HU, 0, 5.55*HU), 0.030, f"clav{s}")
        J(f"loArm{s}", (sx*0.95*HU, 0, 5.55*HU), 0.025, f"upArm{s}")
        J(f"hand{s}",  (sx*1.20*HU, 0, 5.55*HU), 0.028, f"loArm{s}")
        J(f"hip{s}",   (sx*0.12*HU, 0, 3.35*HU), 0.052, "root")
        J(f"knee{s}",  (sx*0.13*HU, 0, 1.9*HU),  0.038, f"hip{s}")
        J(f"foot{s}",  (sx*0.13*HU, 0, 0.15*HU), 0.034, f"knee{s}")
        J(f"toe{s}",   (sx*0.13*HU, -0.13*HU, 0.04*HU), 0.022, f"foot{s}")
    return g, HU

# ---- ENGINE: MESH RAMO A (loft anelli + hub) ----
def frame(d):
    d = d.normalized()
    up = Vector((0,0,1)) if abs(d.z) < 0.95 else Vector((1,0,0))
    N = d.cross(up).normalized(); B = d.cross(N).normalized()
    return d, N, B

def ring(bm, center, N, B, rx, ry, seg):
    return [bm.verts.new(center + N*(rx*math.cos(2*math.pi*i/seg))
                                 + B*(ry*math.sin(2*math.pi*i/seg)))
            for i in range(seg)]

SEG_PROFILE = {
    "limb":  [(0.0,1.15,1.15),(0.12,0.95,0.95),(0.5,0.85,0.85),
              (0.88,0.95,0.95),(1.0,1.15,1.15)],
    "torso": [(0.0,1.0,0.72),(0.5,1.28,0.86),(1.0,1.05,0.78)],
    "neck":  [(0.0,1.0,1.0),(1.0,0.92,0.92)],
}

def build_biped_mesh(graph, seg=12, name="Guardiano"):
    bm = bmesh.new()
    for n, j in graph.items():
        if j["parent"] is None: continue
        p = graph[j["parent"]]
        a, b = p["pos"], j["pos"]
        kind = ("torso" if n.startswith(("spine","root"))
                else "neck" if n in ("neck","head") else "limb")
        prof = SEG_PROFILE[kind]
        d, N, B = frame(b - a)
        prev = None
        for (t, sx, sy) in prof:
            c = a.lerp(b, t)
            rr = p["r"]*(1-t) + j["r"]*t
            cur = ring(bm, c, N, B, rr*sx, rr*sy, seg)
            if prev:
                for i in range(seg):
                    ni = (i+1) % seg
                    bm.faces.new([prev[i], prev[ni], cur[ni], cur[i]])
            prev = cur
    # HUB ai giunti: ico-sfera riempitiva (references/topology.md)
    rmin = min(j["r"] for j in graph.values())
    for n, j in graph.items():
        res = bmesh.ops.create_icosphere(bm, subdivisions=2,
                                         radius=j["r"]*1.16)
        for v in res["verts"]:
            v.co = v.co + j["pos"]
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=rmin*0.35)
    bm.normal_update()
    me = bpy.data.meshes.new(name+"_m"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.modifiers.new("Sub","SUBSURF").levels = 2
    ob.data.shade_smooth()
    return ob

# ---- ENGINE: ARMATURA + POSA ----
def build_armature(graph, mesh_obj, name="Rig"):
    arm = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    bones = {}
    for n, j in graph.items():
        if j["parent"] is None: continue
        b = arm.edit_bones.new(n)
        b.head = graph[j["parent"]]["pos"]
        b.tail = j["pos"]
        bones[n] = b
    for n, b in bones.items():
        pj = graph[n]["parent"]
        if pj and pj in bones: b.parent = bones[pj]
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    mesh_obj.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    cs = mesh_obj.modifiers.new("CorrSmooth","CORRECTIVE_SMOOTH")
    cs.factor = 0.6; cs.iterations = 12
    return rig

POSE_AWAKEN = {
    "spine1": (16,0,0), "spine2": (20,0,0), "neck": (-22,0,0),
    "clavL": (0,0,-8), "clavR": (0,0,8),
    "upArmL": (62,0,-18), "loArmL": (50,0,0),
    "upArmR": (62,0, 18), "loArmR": (50,0,0),
    "hipR": (-95,0,0), "kneeR": (105,0,0), "footR": (35,0,0),
    "hipL": (-48,0,0), "kneeL": (58,0,0),
}
def apply_pose(rig, pose):
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for bn,(rx,ry,rz) in pose.items():
        pb = rig.pose.bones.get(bn)
        if not pb: continue
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (math.radians(rx),math.radians(ry),math.radians(rz))
    bpy.ops.object.mode_set(mode='OBJECT')

# ---- COSTRUZIONE GUARDIANO ----
G, HU = biped_graph(total_h=1.80, heads=7.6)
guard = build_biped_mesh(G, seg=12, name="Guardiano")
rig = build_armature(G, guard, name="Rig")
apply_pose(rig, POSE_AWAKEN)
bpy.context.view_layer.update()

# appoggia a terra + centra, leggermente verso camera (-Y)
dg = bpy.context.evaluated_depsgraph_get()
ge = guard.evaluated_get(dg)
wm = ge.matrix_world
vs = [wm @ v.co for v in ge.to_mesh().vertices]
mnz = min(v.z for v in vs)
cx  = sum(v.x for v in vs)/len(vs)
cy  = sum(v.y for v in vs)/len(vs)
ge.to_mesh_clear()
rig.location += Vector((-cx, -cy - 0.15, -mnz))
bpy.context.view_layer.update()

# posizione MANI reali dopo posa (per luci + sfere emissive)
def bone_tail_world(rig, bn):
    pb = rig.pose.bones.get(bn)
    return rig.matrix_world @ pb.tail
hL = bone_tail_world(rig, "handL")
hR = bone_tail_world(rig, "handR")
hand_mid = (hL + hR) / 2

# ---- MATERIALI personaggio ----
def mat_guard():
    m = bpy.data.materials.new("Guardiano_Mat")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location=(400,0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location=(120,0)
    b.inputs['Base Color'].default_value = (0.030,0.031,0.038,1)
    b.inputs['Roughness'].default_value = 0.7
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    return m

def mat_glow():
    m = bpy.data.materials.new("Luce_Mani")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location=(300,0)
    e = nt.nodes.new('ShaderNodeEmission'); e.location=(60,0)
    e.inputs['Color'].default_value = (1.0,0.48,0.16,1)
    e.inputs['Strength'].default_value = 4.0
    nt.links.new(e.outputs['Emission'], o.inputs['Surface'])
    return m

guard.data.materials.clear()
guard.data.materials.append(mat_guard())
GLOW = mat_glow()
def emis_ball(name, p, r=0.07):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=r, subdivisions=3, location=p)
    o = bpy.context.active_object; o.name = name
    o.data.shade_smooth(); o.data.materials.append(GLOW)
    return o
emis_ball("Mano_L", hL)
emis_ball("Mano_R", hR)

# ============================================================
# SCENA — replica fedele di numeria_awakening _04
# ============================================================
def box(name, cx, cy, cz, sx, sy, sz):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx,cy,cz))
    o = bpy.context.active_object; o.name = name
    o.scale = (sx,sy,sz); bpy.ops.object.transform_apply(scale=True)
    return o

IW, ID, IH, TH = 4.4, 3.8, 3.0, 0.3
rp = []
rp.append(box("Pavimento", 0,0,-TH/2, IW+2*TH, ID+2*TH, TH))
rp.append(box("Soffitto",  0,0,IH+TH/2, IW+2*TH, ID+2*TH, TH))
rp.append(box("Muro_N", 0, ID/2+TH/2, IH/2, IW+2*TH, TH, IH))
rp.append(box("Muro_S", 0,-ID/2-TH/2, IH/2, IW+2*TH, TH, IH))
rp.append(box("Muro_E",  IW/2+TH/2,0,IH/2, TH, ID, IH))
rp.append(box("Muro_O", -IW/2-TH/2,0,IH/2, TH, ID, IH))
slit = box("Cut_Fessura", -IW/2-TH/2, -0.30, IH*0.70, TH*3, 0.24, 1.55)
muroO = rp[5]
md = muroO.modifiers.new("Slit","BOOLEAN")
md.operation='DIFFERENCE'; md.object=slit; md.solver='EXACT'
bpy.context.view_layer.objects.active = muroO
bpy.ops.object.modifier_apply(modifier="Slit")
bpy.data.objects.remove(slit, do_unlink=True)
for o in rp: o.select_set(True)
bpy.context.view_layer.objects.active = rp[0]
bpy.ops.object.join()
room = bpy.context.active_object; room.name = "Stanza"
room.data.shade_smooth()

mst = bpy.data.materials.new("Pietra_Grigia")
mst.use_nodes = True
nt = mst.node_tree; nt.nodes.clear()
o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location=(700,0)
b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location=(340,0)
b.inputs['Roughness'].default_value = 0.92
n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location=(-360,80)
n1.inputs['Scale'].default_value = 4.5; n1.inputs['Detail'].default_value = 8.0
cr = nt.nodes.new('ShaderNodeValToRGB'); cr.location=(-110,80)
cr.color_ramp.elements[0].color = (0.055,0.056,0.062,1)
cr.color_ramp.elements[1].color = (0.140,0.142,0.150,1)
nt.links.new(n1.outputs['Fac'], cr.inputs['Fac'])
nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location=(-360,-240)
n2.inputs['Scale'].default_value = 7.0; n2.inputs['Detail'].default_value = 9.0
n3 = nt.nodes.new('ShaderNodeTexNoise'); n3.location=(-360,-470)
n3.inputs['Scale'].default_value = 35.0
bp1 = nt.nodes.new('ShaderNodeBump'); bp1.location=(-110,-260)
bp1.inputs['Strength'].default_value = 0.55; bp1.inputs['Distance'].default_value = 0.04
bp2 = nt.nodes.new('ShaderNodeBump'); bp2.location=(120,-300)
bp2.inputs['Strength'].default_value = 0.22; bp2.inputs['Distance'].default_value = 0.01
nt.links.new(n2.outputs['Fac'], bp1.inputs['Height'])
nt.links.new(bp1.outputs['Normal'], bp2.inputs['Normal'])
nt.links.new(n3.outputs['Fac'], bp2.inputs['Height'])
nt.links.new(bp2.outputs['Normal'], b.inputs['Normal'])
nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
room.data.materials.append(mst)

# luci
bpy.ops.object.light_add(type='POINT', location=hand_mid+Vector((0,0,0.05)))
key = bpy.context.active_object; key.name="Luce_Mani"
key.data.energy=32; key.data.color=(1.0,0.58,0.26); key.data.shadow_soft_size=0.28

bpy.ops.object.light_add(type='SPOT', location=(-IW/2-TH-0.5,-0.30,IH*0.84))
beam = bpy.context.active_object; beam.name="Raggio_Freddo"
beam.data.energy=2600; beam.data.color=(0.50,0.63,0.97)
beam.data.spot_size=math.radians(38); beam.data.spot_blend=0.30
beam.data.shadow_soft_size=0.04
beam.rotation_euler = Vector((1.0,0.06,-0.66)).to_track_quat('-Z','Y').to_euler()

bpy.ops.object.light_add(type='AREA', location=(-1.8,-1.6,2.4))
amb = bpy.context.active_object; amb.name="Ambiente"
amb.data.energy=11; amb.data.color=(0.38,0.46,0.62); amb.data.size=4.0

world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value=(0.02,0.02,0.03,1.0)
bg.inputs[1].default_value=0.12

bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,IH/2))
vol = bpy.context.active_object; vol.name="Atmosfera"
vol.scale=(IW,ID,IH); bpy.ops.object.transform_apply(scale=True)
vm = bpy.data.materials.new("Pulviscolo")
vm.use_nodes=True; vnt=vm.node_tree; vnt.nodes.clear()
vo=vnt.nodes.new('ShaderNodeOutputMaterial'); vo.location=(300,0)
pv=vnt.nodes.new('ShaderNodeVolumePrincipled'); pv.location=(0,0)
pv.inputs['Color'].default_value=(0.60,0.66,0.80,1)
pv.inputs['Density'].default_value=0.14
if 'Anisotropy' in [i.name for i in pv.inputs]:
    pv.inputs['Anisotropy'].default_value=0.35
vnt.links.new(pv.outputs['Volume'], vo.inputs['Volume'])
vol.data.materials.append(vm)

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0,-0.28,0.78))
tgt = bpy.context.active_object; tgt.name="CamTarget"
bpy.ops.object.camera_add(location=(2.00,1.75,0.78))
cam = bpy.context.active_object; cam.name="Camera"
cam.data.lens=32
cam.data.dof.use_dof=True; cam.data.dof.focus_object=tgt
cam.data.dof.aperture_fstop=3.6
tt=cam.constraints.new('TRACK_TO'); tt.target=tgt
tt.track_axis='TRACK_NEGATIVE_Z'; tt.up_axis='UP_Y'
bpy.context.scene.camera=cam

sc = bpy.context.scene
try:    sc.render.engine="BLENDER_EEVEE_NEXT"
except: sc.render.engine="BLENDER_EEVEE"
ev = sc.eevee
if hasattr(ev,'taa_render_samples'): ev.taa_render_samples=96
if hasattr(ev,'use_shadows'): ev.use_shadows=True
if hasattr(ev,'use_raytracing'): ev.use_raytracing=True
for a,v in (('volumetric_tile_size','2'),('volumetric_samples',128),
            ('volumetric_start',0.05),('volumetric_end',40.0),
            ('use_volumetric_shadows',True)):
    if hasattr(ev,a):
        try: setattr(ev,a,v)
        except: pass
sc.render.resolution_x=1280; sc.render.resolution_y=720
sc.render.filepath="D:/blender-claude/renders/numeria_guardian_02.png"
sc.render.image_settings.file_format='PNG'
sc.render.use_compositing=False
try:
    sc.view_settings.view_transform="AgX"
    for lk in ("AgX - Medium High Contrast","AgX - Base Contrast",
               "AgX - Medium Low Contrast","None"):
        try: sc.view_settings.look=lk; break
        except Exception: continue
except: pass
sc.view_settings.exposure=-0.2
bpy.ops.render.render(write_still=True)

result = {"saved": sc.render.filepath, "ramo": "A (biped autorato)",
          "giunti": len(G), "verts": len(guard.data.vertices)}
