import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"
def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    if "error" in r: print("ERR:", r["error"][:800]); return None
    return r.get("ok")

# Rebuild Cup with sharp junction edges to prevent normal bleeding
code = """
import bpy, bmesh, math

old = bpy.data.objects.get('Cup')
if old:
    bpy.data.objects.remove(old, do_unlink=True)

SEGS = 64
TR = 0.031; BR = 0.0225; H = 0.058; W = 0.004

me = bpy.data.meshes.new('CupMesh')
bm = bmesh.new()

def ring(r, z):
    verts = []
    for i in range(SEGS):
        a = 2 * math.pi * i / SEGS
        verts.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
    return verts

def bridge(ra, rb):
    n = len(ra)
    for i in range(n):
        bm.faces.new([ra[i], ra[(i+1)%n], rb[(i+1)%n], rb[i]])

r_obot = ring(BR, 0.0)
r_otop = ring(TR, H)
r_itop = ring(TR - W, H - 0.001)
r_ibot = ring(BR - W, 0.006)
cen_t  = bm.verts.new((0, 0, 0.006))
cen_b  = bm.verts.new((0, 0, 0.0))

bridge(r_obot, r_otop)
bridge(r_otop, r_itop)
bridge(r_itop, r_ibot)
for i in range(SEGS):
    bm.faces.new([r_ibot[(i+1)%SEGS], r_ibot[i], cen_t])
for i in range(SEGS):
    bm.faces.new([r_obot[i], r_obot[(i+1)%SEGS], cen_b])

bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

# Mark circumferential edges at junction rings as SHARP
# so smooth-shading does NOT bleed across the rim/bottom face transitions
junction_sets = [
    set(id(v) for v in r_obot),
    set(id(v) for v in r_otop),
    set(id(v) for v in r_itop),
    set(id(v) for v in r_ibot),
]
bm.edges.ensure_lookup_table()
for e in bm.edges:
    v0, v1 = id(e.verts[0]), id(e.verts[1])
    for jset in junction_sets:
        if v0 in jset and v1 in jset:
            e.smooth = False
            break

bm.to_mesh(me)
bm.free()

ob = bpy.data.objects.new('Cup', me)
bpy.context.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.shade_smooth()
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
bpy.context.view_layer.update()
bot = min((ob.matrix_world @ v.co).z for v in ob.data.vertices)
ob.location.z -= bot
mat = bpy.data.materials.get('Porcelain')
if mat:
    ob.data.materials.clear()
    ob.data.materials.append(mat)
result = {'verts': len(me.vertices), 'faces': len(me.polygons)}
"""

r = blender(code, timeout=20)
print("Sharp-edge cup:", r)

# Render
code2 = """
import bpy, base64, os, tempfile
sc = bpy.context.scene
try:
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
except:
    sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 1280
sc.render.resolution_y = 960
sc.view_settings.view_transform = 'Filmic'
sc.view_settings.look = 'Medium High Contrast'
sc.view_settings.exposure = -0.1
sc.render.use_compositing = False
tmp = tempfile.mktemp(suffix='.png')
sc.render.filepath = tmp
bpy.ops.render.render(write_still=True)
with open(tmp, 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
os.remove(tmp)
result = {'b64': b64}
"""
rv = blender(code2, timeout=180)
if rv and "b64" in rv:
    img = base64.b64decode(rv["b64"])
    with open("D:/blender-claude/renders/espresso_sharp_edges.png", "wb") as f:
        f.write(img)
    print(f"Saved ({len(img)//1024}KB)")
