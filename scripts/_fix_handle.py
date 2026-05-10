import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"
def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    if "error" in r: print("ERR:", r["error"][:500]); return None
    return r.get("ok")

# Fix handle
r = blender(
    "import bpy, bmesh, math\n"
    "from mathutils import Vector\n"
    "old=bpy.data.objects.get('Handle')\n"
    "if old: bpy.data.objects.remove(old, do_unlink=True)\n"

    "CUP_TOP_R=0.031; ATTACH_Z_TOP=0.048; ATTACH_Z_BOT=0.009\n"
    "DEPTH=0.024; TUBE_R=0.004; SEGS_PATH=20; SEGS_TUBE=10\n"

    "z_mid=(ATTACH_Z_TOP+ATTACH_Z_BOT)/2\n"
    "z_rad=(ATTACH_Z_TOP-ATTACH_Z_BOT)/2\n"

    "path=[]\n"
    "for i in range(SEGS_PATH+1):\n"
    "    t=i/SEGS_PATH\n"
    "    ang=math.pi*t\n"
    "    px=CUP_TOP_R+DEPTH*math.sin(ang)\n"
    "    pz=z_mid+z_rad*math.cos(ang)\n"
    "    path.append(Vector((px,0,pz)))\n"

    "me=bpy.data.meshes.new('HandleMesh')\n"
    "bm=bmesh.new()\n"

    "def tube_ring(bm,center,tangent,r,segs):\n"
    "    ref=Vector((0,1,0))\n"
    "    ax1=tangent.cross(ref)\n"
    "    if ax1.length<0.001: ax1=Vector((1,0,0))\n"
    "    else: ax1=ax1.normalized()\n"
    "    ax2=tangent.cross(ax1).normalized()\n"
    "    ring=[]\n"
    "    for i in range(segs):\n"
    "        a=2*math.pi*i/segs\n"
    "        p=center+(math.cos(a)*ax1+math.sin(a)*ax2)*r\n"
    "        ring.append(bm.verts.new(p))\n"
    "    return ring\n"

    "rings=[]\n"
    "for i,pt in enumerate(path):\n"
    "    if i==0: tang=(path[1]-path[0]).normalized()\n"
    "    elif i==len(path)-1: tang=(path[-1]-path[-2]).normalized()\n"
    "    else: tang=(path[i+1]-path[i-1]).normalized()\n"
    "    rings.append(tube_ring(bm,pt,tang,TUBE_R,SEGS_TUBE))\n"

    "for ri in range(len(rings)-1):\n"
    "    ra=rings[ri]; rb=rings[ri+1]; n=SEGS_TUBE\n"
    "    for i in range(n): bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    "bm.faces.new(rings[0])\n"
    "bm.faces.new(list(reversed(rings[-1])))\n"

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Handle',me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "bpy.ops.object.shade_smooth()\n"
    "mat=bpy.data.materials.get('Porcelain')\n"
    "if mat: ob.data.materials.append(mat)\n"
    "result={'verts':len(me.vertices)}\n",
    timeout=20
)
print("Handle v2:", r)

# Fix luci
r = blender(
    "import bpy, math\n"
    "from mathutils import Vector\n"
    "for ob in [o for o in bpy.data.objects if o.type=='LIGHT']: bpy.data.objects.remove(ob, do_unlink=True)\n"
    "bpy.ops.object.light_add(type='AREA', location=(-0.20,-0.10,0.30))\n"
    "key=bpy.context.active_object; key.data.energy=90; key.data.size=0.2\n"
    "key.rotation_euler=(math.radians(50),0,math.radians(-35))\n"
    "bpy.ops.object.light_add(type='AREA', location=(0.20,0.08,0.12))\n"
    "fill=bpy.context.active_object; fill.data.energy=18; fill.data.size=0.5\n"
    "fill.data.color=(0.85,0.90,1.0)\n"
    "bpy.ops.object.light_add(type='SPOT', location=(-0.02,0.22,0.18))\n"
    "rim=bpy.context.active_object; rim.data.energy=40\n"
    "rim.data.spot_size=math.radians(25)\n"
    "rim.data.color=(1.0,0.96,0.88)\n"
    "d=Vector((0,0,0.03))-rim.location\n"
    "rim.rotation_euler=d.to_track_quat('-Z','Y').to_euler()\n"
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.03,0.03,0.04,1.0)\n"
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.15\n"
    "result={'ok':True}\n",
    timeout=10
)
print("Lights:", r)

# Render v2
code = (
    "import bpy,base64,os,tempfile\n"
    "sc=bpy.context.scene\n"
    "try: sc.render.engine='BLENDER_EEVEE_NEXT'\n"
    "except: sc.render.engine='BLENDER_EEVEE'\n"
    "sc.render.resolution_x=1280; sc.render.resolution_y=960\n"
    "sc.view_settings.view_transform='Filmic'\n"
    "sc.view_settings.look='Medium High Contrast'\n"
    "sc.view_settings.exposure=0.05\n"
    "sc.render.use_compositing=False\n"
    "tmp=tempfile.mktemp(suffix='.png'); sc.render.filepath=tmp\n"
    "bpy.ops.render.render(write_still=True)\n"
    "with open(tmp,'rb') as f: b64=base64.b64encode(f.read()).decode()\n"
    "os.remove(tmp)\n"
    "result={'b64':b64}\n"
)
rv = blender(code, timeout=180)
if rv and "b64" in rv:
    img = base64.b64decode(rv["b64"])
    with open("D:/blender-claude/renders/espresso_v2.png","wb") as f: f.write(img)
    print(f"Saved v2 ({len(img)//1024}KB)")
