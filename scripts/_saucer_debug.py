import urllib.request, json
BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=30):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    return r

r = blender(
    "import bpy, bmesh, math\n"
    "OR=0.0575; SH=0.016; DR=0.028; DD=0.004; SEGS=48\n"
    "me=bpy.data.meshes.new('SaucerMesh')\n"
    "bm=bmesh.new()\n"
    "def ring(bm,r,z):\n"
    "    verts=[]\n"
    "    for i in range(SEGS):\n"
    "        a=2*math.pi*i/SEGS\n"
    "        verts.append(bm.verts.new((r*math.cos(a),r*math.sin(a),z)))\n"
    "    return verts\n"
    "def bridge(bm,ra,rb):\n"
    "    n=len(ra)\n"
    "    for i in range(n): bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    # Geometria semplificata: disco piatto con depressione centrale
    "z0=0.0; z2=SH-DD; z3=SH\n"
    "r1=ring(bm, OR,      z0)\n"  # bordo esterno basso
    "r2=ring(bm, OR,      z3)\n"  # bordo esterno alto
    "r3=ring(bm, DR+0.004,z3)\n"  # piano esterno
    "r4=ring(bm, DR,      z3)\n"  # bordo depressione
    "r5=ring(bm, DR,      z2)\n"  # fondo depressione
    "r6=ring(bm, 0.005,   z2)\n"  # centro
    "cen=bm.verts.new((0,0,z2))\n"

    # fondo depressione
    "for i in range(SEGS): bm.faces.new([r6[i],r6[(i+1)%SEGS],cen])\n"
    "bridge(bm,r6,r5)\n"
    # pareti depressione
    "bridge(bm,r5,r4)\n"
    # piano top
    "bridge(bm,r4,r3)\n"
    "bridge(bm,r3,r2)\n"
    # bordo laterale
    "bridge(bm,r2,r1)\n"
    # fondo piattino
    "cen2=bm.verts.new((0,0,z0))\n"
    "for i in range(SEGS): bm.faces.new([r1[(i+1)%SEGS],r1[i],cen2])\n"

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Saucer',me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "bpy.ops.object.shade_smooth()\n"
    "result={'verts':len(me.vertices),'faces':len(me.polygons)}\n",
    timeout=20
)
print("Saucer:", r)
