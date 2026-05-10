"""
sculpt_apple_test.py
Test della blender-space skill: sculpting procedurale su una mela.
"""
import urllib.request, json, base64, math

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout + 10).read())
    if "error" in r: print("  ERR:", r["error"][:800]); return None
    return r.get("ok")

def render_save(path, w=1280, h=960, exposure=0.05):
    code = (
        "import bpy, base64, os, tempfile\n"
        "sc = bpy.context.scene\n"
        "try: sc.render.engine = 'BLENDER_EEVEE_NEXT'\n"
        "except: sc.render.engine = 'BLENDER_EEVEE'\n"
        f"sc.render.resolution_x={w}; sc.render.resolution_y={h}\n"
        "sc.view_settings.view_transform='Filmic'\n"
        "sc.view_settings.look='Medium High Contrast'\n"
        f"sc.view_settings.exposure={exposure}\n"
        "sc.render.use_compositing=False\n"
        "tmp=tempfile.mktemp(suffix='.png'); sc.render.filepath=tmp\n"
        "bpy.ops.render.render(write_still=True)\n"
        "with open(tmp,'rb') as f: b64=base64.b64encode(f.read()).decode()\n"
        "os.remove(tmp)\n"
        "result={'b64':b64}\n"
    )
    r = blender(code, timeout=180)
    if r and "b64" in r:
        img = base64.b64decode(r["b64"])
        with open(path, "wb") as f: f.write(img)
        print(f"  Saved: {path} ({len(img)//1024}KB)")

# ─── STEP 1: pulisci scena e crea sfera UV ─────────────────────────────────
print("Step 1: create UV sphere...")
STEP1 = (
    "import bpy\n"
    "bpy.ops.object.select_all(action='SELECT')\n"
    "bpy.ops.object.delete()\n"
    "bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, segments=64, ring_count=48, location=(0,0,0))\n"
    "sphere = bpy.context.active_object\n"
    "sphere.name = 'Apple'\n"
    "bpy.ops.object.shade_smooth()\n"
    "bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')\n"
    "result = {'verts': len(sphere.data.vertices), 'loc': list(sphere.location)}\n"
)
print("  Sphere:", blender(STEP1, timeout=15))

# ─── STEP 2: sculpt procedurale ────────────────────────────────────────────
print("Step 2: sculpt brushes...")
SCULPT_LIB = (
    "import bpy, math\n"
    "from mathutils import Vector\n"
    "from mathutils.kdtree import KDTree\n"
    "obj = bpy.data.objects['Apple']\n"

    "def build_kd(obj):\n"
    "    mw = obj.matrix_world\n"
    "    wv = [mw @ v.co for v in obj.data.vertices]\n"
    "    kd = KDTree(len(wv))\n"
    "    for i,v in enumerate(wv): kd.insert(v, i)\n"
    "    kd.balance()\n"
    "    return kd\n"

    "def fo_smooth(d,r):\n"
    "    t=min(d/r,1.0); return 1.0-(3*t*t-2*t*t*t)\n"
    "def fo_sharp(d,r):\n"
    "    t=min(d/r,1.0); return (1.0-t)**3\n"
    "def fo_sphere(d,r):\n"
    "    t=min(d/r,1.0); return math.sqrt(max(0.0,1.0-t*t))\n"
    "def fo_z(d,r):\n"
    "    return max(0.0, 1.0-d/r)\n"
    "FO={'smooth':fo_smooth,'sharp':fo_sharp,'sphere':fo_sphere,'linear':fo_z}\n"

    "def brush(obj, cx,cy,cz, radius, strength, direction='normal', falloff='smooth'):\n"
    "    mw=obj.matrix_world; mwi=mw.inverted(); nm=mw.inverted().transposed().to_3x3()\n"
    "    fn=FO.get(falloff, fo_smooth); kd=build_kd(obj)\n"
    "    hits=kd.find_range(Vector((cx,cy,cz)), radius)\n"
    "    for pos,vi,dist in hits:\n"
    "        v=obj.data.vertices[vi]; w=fn(dist,radius)\n"
    "        if direction=='normal': dw=(nm@v.normal).normalized()*strength*w\n"
    "        elif direction=='z': dw=Vector((0,0,strength*w))\n"
    "        else: dw=Vector(direction).normalized()*strength*w\n"
    "        v.co += mwi.to_3x3()@dw\n"
    "    obj.data.update()\n"
    "    return len(hits)\n"

    # dimple in cima (polo nord schiacciato verso dentro)
    "n1=brush(obj, 0,0,0.12,  0.045, -0.028, 'normal', 'sharp')\n"
    # base appiattita
    "n2=brush(obj, 0,0,-0.12, 0.055, -0.018, 'z',      'sphere')\n"
    # bombatura equatoriale (4 punti)
    "for ad in [0,90,180,270]:\n"
    "    a=math.radians(ad)\n"
    "    brush(obj, 0.12*math.cos(a),0.12*math.sin(a),0, 0.07, 0.008, 'normal','smooth')\n"
    # schiacciamento verticale (mela più larga che alta)
    "for v in obj.data.vertices: v.co.z *= 0.88\n"
    "obj.data.update()\n"
    "result={'dimple':n1,'base':n2,'total_v':len(obj.data.vertices)}\n"
)
print("  Sculpt:", blender(SCULPT_LIB, timeout=30))

# ─── STEP 3: safe_place — base a z=0 ──────────────────────────────────────
print("Step 3: safe_place...")
PLACE = (
    "import bpy\n"
    "from mathutils import Vector\n"
    "obj = bpy.data.objects['Apple']\n"
    "vw=[obj.matrix_world@v.co for v in obj.data.vertices]\n"
    "xs=[v.x for v in vw];ys=[v.y for v in vw];zs=[v.z for v in vw]\n"
    "cx=(min(xs)+max(xs))/2;cy=(min(ys)+max(ys))/2;cz=(min(zs)+max(zs))/2\n"
    "ox=obj.location.x-cx;oy=obj.location.y-cy;oz=obj.location.z-cz\n"
    "bfc=cz-min(zs)\n"
    "obj.location=(0+ox, 0+oy, 0+oz+bfc)\n"
    "vw2=[obj.matrix_world@v.co for v in obj.data.vertices]\n"
    "result={'zmin':round(min(v.z for v in vw2),4),'zmax':round(max(v.z for v in vw2),4)}\n"
)
print("  Place:", blender(PLACE, timeout=10))

# ─── STEP 4: materiale mela rossa ─────────────────────────────────────────
print("Step 4: apple material...")
MAT = (
    "import bpy\n"
    "obj=bpy.data.objects['Apple']\n"
    "mat=bpy.data.materials.new('AppleMat')\n"
    "mat.use_nodes=True\n"
    "try: mat.surface_render_method='DITHERED'\n"
    "except: pass\n"
    "nt=mat.node_tree; nt.nodes.clear()\n"
    "out=nt.nodes.new('ShaderNodeOutputMaterial')\n"
    "bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled')\n"
    "out.location=(300,0); bsdf.location=(0,0)\n"
    "nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])\n"
    "inp=[i.name for i in bsdf.inputs]\n"
    "bsdf.inputs['Roughness'].default_value=0.18\n"
    # coat
    "if 'Coat Weight' in inp: bsdf.inputs['Coat Weight'].default_value=0.55; bsdf.inputs['Coat Roughness'].default_value=0.08\n"
    "elif 'Clearcoat' in inp: bsdf.inputs['Clearcoat'].default_value=0.55\n"
    # specular
    "if 'Specular IOR Level' in inp: bsdf.inputs['Specular IOR Level'].default_value=0.6\n"
    "elif 'Specular' in inp: bsdf.inputs['Specular'].default_value=0.6\n"
    # subsurface
    "for sn in ['Subsurface Weight','Subsurface']:\n"
    "    if sn in inp: bsdf.inputs[sn].default_value=0.12; break\n"
    # noise texture → colorramp rosso/verde
    "noise=nt.nodes.new('ShaderNodeTexNoise'); noise.location=(-500,100)\n"
    "noise.inputs['Scale'].default_value=7.0\n"
    "noise.inputs['Detail'].default_value=5.0\n"
    "noise.inputs['Roughness'].default_value=0.55\n"
    "cr=nt.nodes.new('ShaderNodeValToRGB'); cr.location=(-280,100)\n"
    "cr.color_ramp.elements[0].position=0.35\n"
    "cr.color_ramp.elements[0].color=(0.72,0.04,0.02,1.0)\n"
    "cr.color_ramp.elements[1].position=0.70\n"
    "cr.color_ramp.elements[1].color=(0.50,0.55,0.03,1.0)\n"
    "nt.links.new(noise.outputs['Fac'], cr.inputs['Fac'])\n"
    "nt.links.new(cr.outputs['Color'], bsdf.inputs['Base Color'])\n"
    "obj.data.materials.clear(); obj.data.materials.append(mat)\n"
    "result={'mat':mat.name}\n"
)
print("  Material:", blender(MAT, timeout=15))

# ─── STEP 5: stelo ────────────────────────────────────────────────────────
print("Step 5: stem...")
STEM = (
    "import bpy, math\n"
    "apple=bpy.data.objects['Apple']\n"
    "vw=[apple.matrix_world@v.co for v in apple.data.vertices]\n"
    "top_z=max(v.z for v in vw)\n"
    "bpy.ops.mesh.primitive_cylinder_add(radius=0.006, depth=0.052, location=(0.0,0.0,top_z+0.026))\n"
    "stem=bpy.context.active_object; stem.name='AppleStem'\n"
    "stem.rotation_euler=(0, math.radians(10), 0)\n"
    "bpy.ops.object.shade_smooth()\n"
    "ms=bpy.data.materials.new('StemMat'); ms.use_nodes=True\n"
    "ms.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(0.11,0.06,0.02,1.0)\n"
    "ms.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=0.88\n"
    "stem.data.materials.append(ms)\n"
    "sv=[stem.matrix_world@v.co for v in stem.data.vertices]\n"
    "result={'stem_zmin':round(min(v.z for v in sv),4),'apple_zmax':round(top_z,4)}\n"
)
print("  Stem:", blender(STEM, timeout=10))

# ─── STEP 6: camera + luci ────────────────────────────────────────────────
print("Step 6: scene setup...")
SCENE = (
    "import bpy, math\n"
    "from mathutils import Vector\n"
    # camera
    "bpy.ops.object.camera_add(location=(0.38,-0.50,0.28))\n"
    "cam=bpy.context.active_object; cam.name='Camera'; cam.data.lens=75\n"
    "bpy.context.scene.camera=cam\n"
    "apple=bpy.data.objects['Apple']\n"
    "vw=[apple.matrix_world@v.co for v in apple.data.vertices]\n"
    "cx=(max(v.x for v in vw)+min(v.x for v in vw))/2\n"
    "cy=(max(v.y for v in vw)+min(v.y for v in vw))/2\n"
    "cz=(max(v.z for v in vw)+min(v.z for v in vw))/2\n"
    "d=Vector((cx,cy,cz))-cam.location\n"
    "cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()\n"
    # key light
    "bpy.ops.object.light_add(type='AREA', location=(0.5,-0.25,0.75))\n"
    "key=bpy.context.active_object; key.data.energy=90; key.data.size=0.5\n"
    "key.rotation_euler=(math.radians(38),0,math.radians(28))\n"
    # fill
    "bpy.ops.object.light_add(type='AREA', location=(-0.45,0.15,0.35))\n"
    "fill=bpy.context.active_object; fill.data.energy=22; fill.data.size=0.7\n"
    "fill.data.color=(0.88,0.93,1.0)\n"
    # rim
    "bpy.ops.object.light_add(type='SPOT', location=(0.05,0.55,0.55))\n"
    "rim=bpy.context.active_object; rim.data.energy=55; rim.data.spot_size=math.radians(28)\n"
    "rim.rotation_euler=(math.radians(-55),0,math.radians(180))\n"
    # piano
    "bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0,0,-0.001))\n"
    "pl=bpy.context.active_object; pl.name='Table'\n"
    "mt=bpy.data.materials.new('TableMat'); mt.use_nodes=True\n"
    "mt.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(0.90,0.88,0.84,1.0)\n"
    "mt.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=0.65\n"
    "pl.data.materials.append(mt)\n"
    # world
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.07,0.07,0.09,1.0)\n"
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.4\n"
    "result={'cam':cam.name,'apple_center':[round(cx,3),round(cy,3),round(cz,3)]}\n"
)
print("  Scene:", blender(SCENE, timeout=15))

# ─── STEP 7: render ────────────────────────────────────────────────────────
print("Step 7: render...")
render_save("D:/blender-claude/renders/sculpt_apple_v1.png", w=1280, h=960, exposure=0.05)
print("Done.")
