"""
espresso_v2.py — build dal coordinator build_plan
Pipeline: blender-research → blender-coordinator → blender-arch (questo script)
"""
import urllib.request, json, base64, math

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    if "error" in r: print("  ERR:", r["error"][:600]); return None
    return r.get("ok")

def render_save(path, w=1280, h=960, exposure=-0.1):
    code = (
        "import bpy,base64,os,tempfile\n"
        "sc=bpy.context.scene\n"
        "try: sc.render.engine='BLENDER_EEVEE_NEXT'\n"
        "except: sc.render.engine='BLENDER_EEVEE'\n"
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

# ═══════════════════════════════════════════════════════════════════
# PHASE 0 — CLEAR SCENE
# ═══════════════════════════════════════════════════════════════════
print("Phase 0: clear scene...")
r = blender(
    "import bpy\n"
    "bpy.ops.object.select_all(action='SELECT')\n"
    "bpy.ops.object.delete()\n"
    "result={'ok':True}\n",
    timeout=10
)
print("  Clear:", r)

# ═══════════════════════════════════════════════════════════════════
# PHASE 1 — BODY (tecnica: LATHE via bmesh rings)
# Coordinator notes: profilo 2D ruotato in 48 sezioni
# Rings: foot_ext, foot_int, foot_top, wall_bot_out, wall_bot_in,
#        wall_top_in, rim_out — bridge consecutivi
# ═══════════════════════════════════════════════════════════════════
print("Phase 1: body (LATHE)...")
BODY = (
    "import bpy, bmesh, math\n"
    "SEGS=48\n"
    # Dimensioni dal build_plan (blender_units)
    "TOP_R=0.031; BOT_R=0.0225; H=0.058; WALL=0.0045; BASE=0.007\n"
    "FOOT_H=0.002; FOOT_W=0.003\n"

    "me=bpy.data.meshes.new('CupMesh')\n"
    "bm=bmesh.new()\n"

    "def ring(bm,r,z):\n"
    "    v=[]\n"
    "    for i in range(SEGS):\n"
    "        a=2*math.pi*i/SEGS\n"
    "        v.append(bm.verts.new((r*math.cos(a),r*math.sin(a),z)))\n"
    "    return v\n"

    "def bridge(bm,ra,rb):\n"
    "    n=len(ra)\n"
    "    for i in range(n): bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    # Profilo (bottom → top):
    # foot ring esterno (base tazza, grezzo)
    "r_fext = ring(bm, BOT_R,          0.0)\n"
    # foot ring interno
    "r_fint = ring(bm, BOT_R-FOOT_W,   0.0)\n"
    # top del foot ring
    "r_ftop = ring(bm, BOT_R-FOOT_W,   FOOT_H)\n"
    # parete esterna base (dal foot ring sale)
    "r_wbot = ring(bm, BOT_R,          FOOT_H)\n"
    # parete esterna top / bordo
    "r_wtop = ring(bm, TOP_R,          H)\n"
    # parete interna top (rientra di WALL)
    "r_itp  = ring(bm, TOP_R-WALL,     H-0.001)\n"
    # parete interna base (rientra ancora per il taper)
    "r_ibt  = ring(bm, BOT_R-WALL,     BASE)\n"
    # centro fondo interno
    "r_icen = ring(bm, 0.006,          BASE)\n"
    "cen    = bm.verts.new((0,0,BASE))\n"

    # Costruzione:
    # 1. Fondo esterno (piano tra foot_int e foot_ext)
    "bridge(bm, r_fint, r_fext)\n"
    # 2. Sotto il foot ring (fondo tazza che tocca il tavolo)
    # fan dal centro verso r_fint
    "cen_bot=bm.verts.new((0,0,0.0))\n"
    "for i in range(SEGS): bm.faces.new([r_fint[(i+1)%SEGS],r_fint[i],cen_bot])\n"
    # 3. Lato interno foot ring
    "bridge(bm, r_ftop, r_fint)\n"
    # 4. Fondo piatto tra foot ring e parete
    "bridge(bm, r_wbot, r_ftop)\n"
    # 5. Parete esterna
    "bridge(bm, r_wtop, r_wbot)\n"
    # 6. Rim (piano superiore bordo)
    "bridge(bm, r_itp, r_wtop)\n"
    # 7. Parete interna
    "bridge(bm, r_ibt, r_itp)\n"
    # 8. Fondo interno (piano)
    "bridge(bm, r_icen, r_ibt)\n"
    # 9. Centro fondo interno
    "for i in range(SEGS): bm.faces.new([r_icen[i],r_icen[(i+1)%SEGS],cen])\n"

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Cup',me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "ob.data.shade_smooth()\n"  # CORRETTO: metodo diretto, non ops (bug bmesh)
    "bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY',center='BOUNDS')\n"
    # safe_place: base a z=0
    "bpy.context.view_layer.update()\n"
    "vw=[ob.matrix_world@v.co for v in ob.data.vertices]\n"
    "bot=min(v.z for v in vw)\n"
    "ob.location.z-=bot\n"
    "bpy.context.view_layer.update()\n"
    "vw2=[ob.matrix_world@v.co for v in ob.data.vertices]\n"
    "result={'verts':len(me.vertices),'zmin':round(min(v.z for v in vw2),4),'zmax':round(max(v.z for v in vw2),4)}\n"
)
print("  Body:", blender(BODY, timeout=20))

# ═══════════════════════════════════════════════════════════════════
# PHASE 2 — HANDLE (tecnica: CURVE_LOOP)
# Coordinator notes: 21 pt semicerchio XZ, sezione circolare r=0.004
# Tangente interpolata su 3 punti, ax1/ax2 perpendicolari
# ═══════════════════════════════════════════════════════════════════
print("Phase 2: handle (CURVE_LOOP)...")
HANDLE = (
    "import bpy, bmesh, math\n"
    "from mathutils import Vector\n"
    # Dimensioni dal build_plan
    "TOP_R=0.031; ATZ_TOP=0.048; ATZ_BOT=0.009\n"
    "DEPTH=0.024; TUBE_R=0.004; NP=20; NT=10\n"

    "z_mid=(ATZ_TOP+ATZ_BOT)/2\n"
    "z_rad=(ATZ_TOP-ATZ_BOT)/2\n"

    # Path semicircolare (piano XZ)
    "path=[]\n"
    "for i in range(NP+1):\n"
    "    ang=math.pi*i/NP\n"
    "    path.append(Vector((TOP_R+DEPTH*math.sin(ang), 0, z_mid+z_rad*math.cos(ang))))\n"

    "me=bpy.data.meshes.new('HandleMesh')\n"
    "bm=bmesh.new()\n"

    "def tube_ring(bm,center,tangent,r,segs):\n"
    "    ref=Vector((0,1,0))\n"
    "    ax1=tangent.cross(ref)\n"
    "    ax1=ax1.normalized() if ax1.length>0.001 else Vector((1,0,0))\n"
    "    ax2=tangent.cross(ax1).normalized()\n"
    "    return [bm.verts.new(center+(math.cos(2*math.pi*i/segs)*ax1+math.sin(2*math.pi*i/segs)*ax2)*r) for i in range(segs)]\n"

    "rings=[]\n"
    "for i,pt in enumerate(path):\n"
    "    if i==0: tang=(path[1]-path[0]).normalized()\n"
    "    elif i==len(path)-1: tang=(path[-1]-path[-2]).normalized()\n"
    "    else: tang=(path[i+1]-path[i-1]).normalized()\n"
    "    rings.append(tube_ring(bm,pt,tang,TUBE_R,NT))\n"

    "for ri in range(len(rings)-1):\n"
    "    ra=rings[ri]; rb=rings[ri+1]\n"
    "    for i in range(NT): bm.faces.new([ra[i],ra[(i+1)%NT],rb[(i+1)%NT],rb[i]])\n"
    "bm.faces.new(rings[0])\n"
    "bm.faces.new(list(reversed(rings[-1])))\n"

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Handle',me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "ob.data.shade_smooth()\n"  # CORRETTO: metodo diretto, non ops (bug bmesh)
    "result={'verts':len(me.vertices)}\n"
)
print("  Handle:", blender(HANDLE, timeout=20))

# ═══════════════════════════════════════════════════════════════════
# PHASE 3 — SAUCER (tecnica: DISC con rings concentrici)
# Coordinator notes: center→dep_bot→dep_in→dep_out→outer, bridge+fan
# Position: below body via world_bounds
# ═══════════════════════════════════════════════════════════════════
print("Phase 3: saucer (DISC)...")
SAUCER = (
    "import bpy, bmesh, math\n"
    # Dimensioni dal build_plan
    "OR=0.0575; SH=0.016; DR=0.028; DD=0.004; SEGS=48\n"

    "me=bpy.data.meshes.new('SaucerMesh')\n"
    "bm=bmesh.new()\n"

    "def ring(bm,r,z):\n"
    "    v=[]\n"
    "    for i in range(SEGS):\n"
    "        a=2*math.pi*i/SEGS\n"
    "        v.append(bm.verts.new((r*math.cos(a),r*math.sin(a),z)))\n"
    "    return v\n"

    "def bridge(bm,ra,rb):\n"
    "    n=len(ra)\n"
    "    for i in range(n): bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    "z_top=SH; z_dep=SH-DD; z_bot=0.0\n"

    # Rings dal centro verso l'esterno, poi fondo
    "r_cen =ring(bm, 0.005,  z_dep)\n"
    "r_db  =ring(bm, DR,     z_dep)\n"
    "r_di  =ring(bm, DR,     z_top)\n"
    "r_do  =ring(bm, DR+0.004, z_top)\n"
    "r_out =ring(bm, OR,     z_top)\n"
    "r_obot=ring(bm, OR,     z_bot)\n"

    # Centro depressione (fan)
    "cen=bm.verts.new((0,0,z_dep))\n"
    "for i in range(SEGS): bm.faces.new([r_cen[i],r_cen[(i+1)%SEGS],cen])\n"

    # Bridge: centro → su → fuori
    "bridge(bm,r_cen,r_db)\n"    # fondo dep (piatto)
    "bridge(bm,r_db, r_di)\n"    # parete depressione (verticale)
    "bridge(bm,r_di, r_do)\n"    # piano interno saucer
    "bridge(bm,r_do, r_out)\n"   # piano esterno saucer
    "bridge(bm,r_out,r_obot)\n"  # bordo laterale

    # Fondo piattino (fan dal centro)
    "cen2=bm.verts.new((0,0,z_bot))\n"
    "for i in range(SEGS): bm.faces.new([r_obot[(i+1)%SEGS],r_obot[i],cen2])\n"

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Saucer',me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "ob.data.shade_smooth()\n"  # CORRETTO: metodo diretto, non ops (bug bmesh)

    # Position: below body (world_bounds)
    "cup=bpy.data.objects['Cup']\n"
    "bpy.context.view_layer.update()\n"
    "cv=[cup.matrix_world@v.co for v in cup.data.vertices]\n"
    "cup_bot=min(v.z for v in cv)\n"
    "ob.location.z=cup_bot-SH-0.001\n"
    "bpy.context.view_layer.update()\n"
    "sv=[ob.matrix_world@v.co for v in ob.data.vertices]\n"
    "result={'verts':len(me.vertices),'zmin':round(min(v.z for v in sv),4)}\n"
)
print("  Saucer:", blender(SAUCER, timeout=20))

# ═══════════════════════════════════════════════════════════════════
# PHASE 4 — MATERIAL (Porcelain, condiviso su tutti e 3)
# Coordinator: 1 solo materiale, ShaderNodeMix RGBA (non MixRGB)
# ═══════════════════════════════════════════════════════════════════
print("Phase 4: material (Porcelain)...")
MAT = (
    "import bpy\n"
    "COL=(0.955,0.940,0.896,1.0)\n"
    "mat=bpy.data.materials.new('Porcelain')\n"
    "mat.use_nodes=True\n"
    "nt=mat.node_tree; nt.nodes.clear()\n"
    "out =nt.nodes.new('ShaderNodeOutputMaterial'); out.location=(500,0)\n"
    "bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled');  bsdf.location=(100,0)\n"
    "nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])\n"
    "inp=[i.name for i in bsdf.inputs]\n"
    # Colore base avorio
    "bsdf.inputs['Base Color'].default_value=COL\n"
    "bsdf.inputs['Roughness'].default_value=0.08\n"
    "bsdf.inputs['IOR'].default_value=1.52\n"
    # Coat (smalto lucido)
    "if 'Coat Weight' in inp:\n"
    "    bsdf.inputs['Coat Weight'].default_value=0.2\n"
    "    bsdf.inputs['Coat Roughness'].default_value=0.05\n"
    "elif 'Clearcoat' in inp:\n"
    "    bsdf.inputs['Clearcoat'].default_value=0.2\n"
    # Specular
    "if 'Specular IOR Level' in inp: bsdf.inputs['Specular IOR Level'].default_value=0.55\n"
    "elif 'Specular' in inp: bsdf.inputs['Specular'].default_value=0.55\n"
    # Micro-variazione noise sulla roughness (2%) via ShaderNodeMix RGBA
    "noise=nt.nodes.new('ShaderNodeTexNoise'); noise.location=(-300,100)\n"
    "noise.inputs['Scale'].default_value=12.0\n"
    "noise.inputs['Detail'].default_value=2.0\n"
    "noise.inputs['Roughness'].default_value=0.5\n"
    # Mix colore: avorio scuro ↔ avorio chiaro (variazione minima)
    "mix=nt.nodes.new('ShaderNodeMix'); mix.data_type='RGBA'\n"
    "mix.blend_type='MIX'; mix.location=(-100,100)\n"
    "mix.inputs[6].default_value=(0.930,0.915,0.870,1.0)\n"  # A: avorio scuro
    "mix.inputs[7].default_value=(0.970,0.960,0.930,1.0)\n"  # B: avorio chiaro
    "nt.links.new(noise.outputs['Fac'], mix.inputs[0])\n"
    "nt.links.new(mix.outputs[2], bsdf.inputs['Base Color'])\n"
    # Applica a tutte le parti
    "for name in ['Cup','Handle','Saucer']:\n"
    "    ob=bpy.data.objects.get(name)\n"
    "    if ob: ob.data.materials.clear(); ob.data.materials.append(mat)\n"
    "result={'mat':mat.name,'applied_to':['Cup','Handle','Saucer']}\n"
)
print("  Material:", blender(MAT, timeout=15))

# ═══════════════════════════════════════════════════════════════════
# PHASE 5 — SCENE (camera + lights dal build_plan, tavolo)
# Coordinator: preset small_object, camera calcolata automaticamente
# ═══════════════════════════════════════════════════════════════════
print("Phase 5: scene setup...")
SCENE = (
    "import bpy, math\n"
    "from mathutils import Vector\n"

    # Camera (posizione calcolata dal coordinator)
    "bpy.ops.object.camera_add(location=(0.095,-0.114,0.133))\n"
    "cam=bpy.context.active_object; cam.name='Camera'; cam.data.lens=85\n"
    "bpy.context.scene.camera=cam\n"
    "d=Vector((0,0,0.029))-cam.location\n"
    "cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()\n"

    # Key light (AREA, sinistra-alto)
    "bpy.ops.object.light_add(type='AREA',location=(-0.3,-0.15,0.4))\n"
    "key=bpy.context.active_object; key.data.energy=80; key.data.size=0.25\n"
    "key.rotation_euler=(math.radians(50),0,math.radians(-35))\n"

    # Fill light (AREA, destra, fredda)
    "bpy.ops.object.light_add(type='AREA',location=(0.3,0.1,0.2))\n"
    "fill=bpy.context.active_object; fill.data.energy=20; fill.data.size=0.5\n"
    "fill.data.color=(0.85,0.90,1.0)\n"

    # Rim light (SPOT, dietro, caldo)
    "bpy.ops.object.light_add(type='SPOT',location=(0.0,0.3,0.3))\n"
    "rim=bpy.context.active_object; rim.data.energy=45\n"
    "rim.data.spot_size=math.radians(25)\n"
    "rim.data.color=(1.0,0.96,0.88)\n"
    "d2=Vector((0,0,0.029))-rim.location\n"
    "rim.rotation_euler=d2.to_track_quat('-Z','Y').to_euler()\n"

    # Tavolo (legno scuro caldo)
    "bpy.ops.mesh.primitive_plane_add(size=1.0,location=(0,0,-0.002))\n"
    "pl=bpy.context.active_object; pl.name='Table'\n"
    "mt=bpy.data.materials.new('TableMat'); mt.use_nodes=True\n"
    "tb=mt.node_tree.nodes['Principled BSDF']\n"
    "tb.inputs['Base Color'].default_value=(0.10,0.07,0.04,1.0)\n"
    "tb.inputs['Roughness'].default_value=0.55\n"
    "pl.data.materials.append(mt)\n"

    # World: grigio scuro neutro
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.03,0.03,0.04,1.0)\n"
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.15\n"
    "result={'cam':cam.name}\n"
)
print("  Scene:", blender(SCENE, timeout=15))

# ═══════════════════════════════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════════════════════════════
print("Render...")
render_save("D:/blender-claude/renders/espresso_v2_final.png", w=1280, h=960, exposure=-0.1)
print("Done.")
