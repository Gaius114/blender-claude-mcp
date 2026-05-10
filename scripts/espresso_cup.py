"""
espresso_cup.py — modellato dai dati reali della blender-research skill
BLENDER_VALUES dal spec_sheet (unità Blender = metri):
  body:   top_r=0.031, bot_r=0.0225, h=0.058, wall=0.0045, base=0.007
  handle: loop_h=0.034, depth=0.025, bar 0.010x0.007
  saucer: outer_r=0.0575, h=0.016, dep_r=0.028, dep_depth=0.004
  color:  linear (0.955, 0.940, 0.896)  roughness_glaze=0.08  foot=0.70
"""
import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    if "error" in r: print("  ERR:", r["error"][:600]); return None
    return r.get("ok")

def render_save(path, w=1280, h=960, exposure=0.0):
    code = (
        "import bpy, base64, os, tempfile\n"
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

# ─── STEP 1: pulisci + corpo tazza ─────────────────────────────────────────
print("Step 1: cup body...")
r = blender(
    "import bpy, bmesh, math\n"
    "from mathutils import Vector\n"
    "bpy.ops.object.select_all(action='SELECT')\n"
    "bpy.ops.object.delete()\n"

    # Corpo: cono troncato con bmesh (anelli top e bottom)
    # Dati spec_sheet: top_r=0.031, bot_r=0.0225, h=0.058
    # wall=0.0045, base_thick=0.007
    "TOP_R=0.031; BOT_R=0.0225; H=0.058; WALL=0.0045; BASE=0.007; SEGS=48\n"

    "me=bpy.data.meshes.new('CupMesh')\n"
    "bm=bmesh.new()\n"

    # Costruisci il profilo: cerchi concentrici per fondo + pareti + bordo
    "def ring(bm, r, z, segs):\n"
    "    verts=[]\n"
    "    for i in range(segs):\n"
    "        a=2*math.pi*i/segs\n"
    "        verts.append(bm.verts.new((r*math.cos(a), r*math.sin(a), z)))\n"
    "    return verts\n"

    # Sequenza dei ring dal basso verso l'alto:
    # 0: base esterna bot (foot ring esterno)
    # 1: base interna bot (foot ring interno)
    # 2: inner bottom (fondo interno tazza)
    # 3: inner wall base
    # 4: inner wall top
    # 5: outer wall base
    # 6: outer wall top
    # 7: rim (bordo arrotondato - uguale outer top spostato)

    "foot_r_out = BOT_R\n"               # 0.0225
    "foot_r_in  = BOT_R - 0.003\n"       # 0.0195 — spessore foot ring
    "foot_z     = 0.0\n"
    "foot_top_z = 0.002\n"               # anello alto 2mm

    "inner_bot_r = BOT_R - WALL\n"       # 0.018
    "inner_top_r = TOP_R - WALL\n"       # 0.0265
    "inner_bot_z = BASE\n"               # 0.007
    "inner_top_z = H - 0.001\n"

    "outer_bot_z = 0.0\n"
    "outer_top_z = H\n"

    # rings
    "r0=ring(bm, foot_r_out,  foot_z,     SEGS)\n"   # piede esterno base
    "r1=ring(bm, foot_r_in,   foot_z,     SEGS)\n"   # piede interno base
    "r2=ring(bm, foot_r_in,   foot_top_z, SEGS)\n"   # piede interno top
    "r3=ring(bm, inner_bot_r, foot_top_z, SEGS)\n"   # parete interna base
    "r4=ring(bm, inner_bot_r, inner_bot_z,SEGS)\n"   # fondo interno
    "r5=ring(bm, 0.005,       inner_bot_z,SEGS)\n"   # centro fondo (per chiudere)
    "r6=ring(bm, inner_top_r, inner_top_z,SEGS)\n"   # parete interna top
    "r7=ring(bm, TOP_R,       outer_top_z,SEGS)\n"   # bordo esterno top
    "r8=ring(bm, BOT_R,       outer_bot_z,SEGS)\n"   # parete esterna base

    # Chiudi il centro del fondo
    "bm.verts.ensure_lookup_table()\n"
    "center=bm.verts.new((0,0,inner_bot_z))\n"

    # Connetti anelli con bridge (quads)
    "def bridge(bm, ra, rb):\n"
    "    n=len(ra)\n"
    "    for i in range(n):\n"
    "        bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    # Fondo tazza (fondo interno → center)
    "for i in range(len(r5)):\n"
    "    bm.faces.new([r5[i], r5[(i+1)%len(r5)], center])\n"
    "bridge(bm, r5, r4)\n"       # fondo piatto interno

    # Pareti interne (da fondo su)
    "bridge(bm, r4, r3)\n"       # fondo → parete interna bassa
    "bridge(bm, r3, r2)\n"

    # Foot ring
    "bridge(bm, r1, r0)\n"       # sotto foot ring (anello grezzo)
    "bridge(bm, r2, r1)\n"       # lato interno foot ring

    # Chiudi il fondo esterno (piatto di appoggio)
    "for i in range(len(r0)):\n"
    "    bm.faces.new([r0[(i+1)%len(r0)], r0[i], r8[(i+1)%len(r8)], r8[i]])\n"
    # Aspetta — r0 e r8 hanno lo stesso z=0 ma raggi diversi
    # Bridge diretto
    "bridge(bm, r0, r8)\n"       # fondo esterno (grezzo tra foot ring e parete)

    # Pareti esterne
    "bridge(bm, r8, r7)\n"       # parete esterna (dal basso al bordo)

    # Bordo superiore (rim): collega interno ed esterno
    "bridge(bm, r6, r7)\n"       # rim plate

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Cup', me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "bpy.ops.object.shade_smooth()\n"
    "bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')\n"

    # safe_place: base a z=0
    "bpy.context.view_layer.update()\n"
    "vw=[ob.matrix_world@v.co for v in ob.data.vertices]\n"
    "bot=min(v.z for v in vw)\n"
    "ob.location.z -= bot\n"
    "bpy.context.view_layer.update()\n"

    "result={'verts':len(me.vertices), 'faces':len(me.polygons)}\n",
    timeout=20
)
print("  Body:", r)

# ─── STEP 2: manico ────────────────────────────────────────────────────────
print("Step 2: handle...")
r = blender(
    "import bpy, bmesh, math\n"
    "from mathutils import Vector, Matrix\n"

    # Manico: curva a D estrusa con sezione ovale
    # loop_h=0.034, depth=0.025, bar_w=0.010, bar_h=0.007
    # attach_top_z = cup_h - 0.009 ≈ 0.049
    # attach_bot_z = 0.009
    # Il loop parte dal lato del corpo (x ≈ top_r = 0.031)

    "cup=bpy.data.objects['Cup']\n"
    "bpy.context.view_layer.update()\n"
    "cup_vw=[cup.matrix_world@v.co for v in cup.data.vertices]\n"
    "cup_h=max(v.z for v in cup_vw)\n"   # altezza reale in world

    # Quote manico
    "TOP_R=0.031\n"
    "ATTACH_Z_TOP = cup_h - 0.009\n"
    "ATTACH_Z_BOT = 0.009\n"
    "LOOP_DEPTH   = 0.025\n"
    "BAR_W=0.010; BAR_H=0.007\n"
    "SEGS_LOOP=24; SEGS_PROF=12\n"

    # Costruisci il loop del manico con bmesh:
    # Il loop è una D: lato dritto (attaccato alla tazza) + arco semicircolare
    # Punti del loop (in XZ plane, x=lato della tazza):
    "x0 = TOP_R - 0.002\n"   # punto di attacco sul corpo (leggermente dentro)
    "x1 = TOP_R + LOOP_DEPTH\n"   # massima sporgenza

    "z_top = ATTACH_Z_TOP\n"
    "z_bot = ATTACH_Z_BOT\n"
    "z_mid = (z_top + z_bot) / 2\n"
    "z_rad = (z_top - z_bot) / 2\n"

    # Loop points: arco semicircolare sul lato +x
    "loop_pts=[]\n"
    "N=SEGS_LOOP\n"
    "for i in range(N+1):\n"
    "    t=i/N\n"
    "    if t<=0.5:\n"       # metà superiore: dal top_attach all'apice
    "        ang=math.pi*(t/0.5)\n"
    "        x=x0+LOOP_DEPTH*(1-math.cos(ang))/2\n"
    "        z=z_top - (z_rad*(1-math.cos(ang)))\n"
    "    else:\n"             # metà inferiore: dall'apice al bot_attach
    "        ang=math.pi*((t-0.5)/0.5)\n"
    "        x=x0+LOOP_DEPTH*(1+math.cos(ang))/2\n"
    "        z=z_bot + (z_rad*(1+math.cos(ang)))\n"
    "    loop_pts.append(Vector((x,0,z)))\n"

    # Profilo D della sezione (ovale schiacciato)
    "def d_profile(w,h,segs):\n"
    "    pts=[]\n"
    "    for i in range(segs):\n"
    "        a=2*math.pi*i/segs\n"
    "        pts.append(Vector((math.cos(a)*w/2, math.sin(a)*h/2, 0)))\n"
    "    return pts\n"
    "profile=d_profile(BAR_W, BAR_H, SEGS_PROF)\n"

    # Estrudi il profilo lungo il loop
    "me=bpy.data.meshes.new('HandleMesh')\n"
    "bm=bmesh.new()\n"

    "all_rings=[]\n"
    "for pi, pt in enumerate(loop_pts):\n"
    "    # tangente al loop per orientare il profilo\n"
    "    if pi==0: tang=(loop_pts[1]-loop_pts[0]).normalized()\n"
    "    elif pi==len(loop_pts)-1: tang=(loop_pts[-1]-loop_pts[-2]).normalized()\n"
    "    else: tang=(loop_pts[pi+1]-loop_pts[pi-1]).normalized()\n"
    "    # matrice di rotazione: Z locale → tang\n"
    "    up=Vector((0,1,0))\n"
    "    side=tang.cross(up).normalized()\n"
    "    up2=side.cross(tang).normalized()\n"
    "    rot=Matrix([side,up2,tang]).transposed()\n"
    "    ring=[]\n"
    "    for pv in profile:\n"
    "        wp=pt+rot@pv\n"
    "        ring.append(bm.verts.new(wp))\n"
    "    all_rings.append(ring)\n"

    # Connetti anelli
    "n=SEGS_PROF\n"
    "for ri in range(len(all_rings)-1):\n"
    "    ra=all_rings[ri]; rb=all_rings[ri+1]\n"
    "    for i in range(n):\n"
    "        bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    # Chiudi le estremità (caps)
    "def cap(bm,ring): bm.faces.new(ring)\n"
    "cap(bm, all_rings[0])\n"
    "cap(bm, list(reversed(all_rings[-1])))\n"

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Handle', me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "bpy.ops.object.shade_smooth()\n"
    "result={'verts':len(me.vertices)}\n",
    timeout=20
)
print("  Handle:", r)

# ─── STEP 3: piattino ──────────────────────────────────────────────────────
print("Step 3: saucer...")
r = blender(
    "import bpy, bmesh, math\n"
    # Dati: outer_r=0.0575, h=0.016, dep_r=0.028, dep_depth=0.004
    "OR=0.0575; SH=0.016; DR=0.028; DD=0.004; WT=0.003; SEGS=48\n"

    "me=bpy.data.meshes.new('SaucerMesh')\n"
    "bm=bmesh.new()\n"

    "def ring(bm,r,z):\n"
    "    import math\n"
    "    verts=[]\n"
    "    for i in range(SEGS):\n"
    "        a=2*math.pi*i/SEGS\n"
    "        verts.append(bm.verts.new((r*math.cos(a),r*math.sin(a),z)))\n"
    "    return verts\n"

    "def bridge(bm,ra,rb):\n"
    "    n=len(ra)\n"
    "    for i in range(n): bm.faces.new([ra[i],ra[(i+1)%n],rb[(i+1)%n],rb[i]])\n"

    # Rings dal basso verso l'alto:
    # foot ring esterno base → foot ring interno base → superficie piatta →
    # depression outer rim → depression inner rim → depression bottom
    "z0=0.0\n"              # fondo
    "z1=WT\n"               # top foot ring
    "z2=SH-DD\n"            # piano principale (sotto depression)
    "z3=SH\n"               # top saucer (piano attorno alla cup)

    "foot_out=OR-0.003\n"
    "foot_in =OR-0.006\n"

    "r_foot_out=ring(bm,OR,      z0)\n"
    "r_foot_in =ring(bm,foot_in, z0)\n"
    "r_foot_top=ring(bm,foot_in, z1)\n"
    "r_outer_z1=ring(bm,OR,      z1)\n"     # bordo esterno al livello foot ring
    "r_outer_z3=ring(bm,OR,      z3)\n"     # bordo esterno top
    "r_dep_out =ring(bm,DR+0.004,z3)\n"     # outer rim of depression
    "r_dep_in  =ring(bm,DR,      z3)\n"     # inner rim
    "r_dep_bot =ring(bm,DR,      z2)\n"     # fondo depression
    "r_dep_cen =ring(bm,0.005,   z2)\n"     # centro fondo depression

    # centro fondo depression
    "cen=bm.verts.new((0,0,z2))\n"
    "for i in range(SEGS):\n"
    "    bm.faces.new([r_dep_cen[i],r_dep_cen[(i+1)%SEGS],cen])\n"
    "bridge(bm,r_dep_cen,r_dep_bot)\n"

    # pareti depression
    "bridge(bm,r_dep_bot,r_dep_in)\n"

    # piano top del piattino
    "bridge(bm,r_dep_in, r_dep_out)\n"     # piano interno
    "bridge(bm,r_dep_out,r_outer_z3)\n"    # piano esterno

    # bordo esterno (cilindro verticale)
    "bridge(bm,r_outer_z3,r_outer_z1)\n"

    # foot ring
    "bridge(bm,r_outer_z1,r_foot_out)\n"   # fondo esterno
    "bridge(bm,r_foot_top,r_foot_in)\n"
    "bridge(bm,r_foot_in, r_foot_out)\n"   # sotto foot ring

    # lato interno foot ring
    "bridge(bm,r_foot_out,r_outer_z1)\n"   # chiudi

    "bm.to_mesh(me); bm.free()\n"
    "ob=bpy.data.objects.new('Saucer',me)\n"
    "bpy.context.collection.objects.link(ob)\n"
    "bpy.context.view_layer.objects.active=ob\n"
    "bpy.ops.object.shade_smooth()\n"

    # Posiziona piattino SOTTO la tazza
    "cup=bpy.data.objects['Cup']\n"
    "bpy.context.view_layer.update()\n"
    "cup_vw=[cup.matrix_world@v.co for v in cup.data.vertices]\n"
    "cup_bot=min(v.z for v in cup_vw)\n"
    "ob.location.z=cup_bot-SH\n"   # piattino sotto la base della tazza
    "bpy.context.view_layer.update()\n"
    "result={'verts':len(me.vertices)}\n",
    timeout=20
)
print("  Saucer:", r)

# ─── STEP 4: materiale porcellana ──────────────────────────────────────────
print("Step 4: porcelain material...")
r = blender(
    "import bpy\n"
    # Colore: bianco avorio lineare (0.955, 0.940, 0.896)
    "COL=(0.955, 0.940, 0.896, 1.0)\n"

    "def porcelain_mat(name):\n"
    "    mat=bpy.data.materials.new(name)\n"
    "    mat.use_nodes=True\n"
    "    nt=mat.node_tree; nt.nodes.clear()\n"
    "    out =nt.nodes.new('ShaderNodeOutputMaterial'); out.location=(400,0)\n"
    "    bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled');  bsdf.location=(0,0)\n"
    "    nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])\n"
    "    inp=[i.name for i in bsdf.inputs]\n"
    "    bsdf.inputs['Base Color'].default_value=COL\n"
    "    bsdf.inputs['Roughness'].default_value=0.08\n"    # smalto lucido
    "    if 'Coat Weight' in inp:\n"
    "        bsdf.inputs['Coat Weight'].default_value=0.2\n"
    "        bsdf.inputs['Coat Roughness'].default_value=0.05\n"
    "    elif 'Clearcoat' in inp:\n"
    "        bsdf.inputs['Clearcoat'].default_value=0.2\n"
    "    if 'Specular IOR Level' in inp:\n"
    "        bsdf.inputs['Specular IOR Level'].default_value=0.55\n"
    "    elif 'Specular' in inp:\n"
    "        bsdf.inputs['Specular'].default_value=0.55\n"
    "    bsdf.inputs['IOR'].default_value=1.52\n"
    "    return mat\n"

    "mat=porcelain_mat('Porcelain')\n"
    "for name in ['Cup','Handle','Saucer']:\n"
    "    ob=bpy.data.objects.get(name)\n"
    "    if ob:\n"
    "        ob.data.materials.clear()\n"
    "        ob.data.materials.append(mat)\n"
    "result={'mat':mat.name}\n",
    timeout=10
)
print("  Material:", r)

# ─── STEP 5: camera + luci ─────────────────────────────────────────────────
print("Step 5: scene setup...")
r = blender(
    "import bpy, math\n"
    "from mathutils import Vector\n"

    # Camera leggermente dall'alto e laterale
    "bpy.ops.object.camera_add(location=(0.22,-0.28,0.14))\n"
    "cam=bpy.context.active_object; cam.name='Camera'; cam.data.lens=85\n"
    "bpy.context.scene.camera=cam\n"

    # Punta verso il centro della tazza (z≈0.03)
    "d=Vector((0,0,0.03))-cam.location\n"
    "cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()\n"

    # Key light (sinistra-alto, crea riflesso sullo smalto)
    "bpy.ops.object.light_add(type='AREA', location=(-0.30,-0.15,0.35))\n"
    "key=bpy.context.active_object; key.data.energy=60; key.data.size=0.25\n"
    "key.rotation_euler=(math.radians(45),0,math.radians(-40))\n"

    # Fill (destra-basso, morbido)
    "bpy.ops.object.light_add(type='AREA', location=(0.25,0.10,0.18))\n"
    "fill=bpy.context.active_object; fill.data.energy=20; fill.data.size=0.4\n"
    "fill.data.color=(0.9,0.93,1.0)\n"

    # Rim (dietro, per bordo brillante)
    "bpy.ops.object.light_add(type='SPOT', location=(0.05,0.30,0.25))\n"
    "rim=bpy.context.active_object; rim.data.energy=45\n"
    "rim.data.spot_size=math.radians(35)\n"
    "d2=Vector((0,0,0.03))-rim.location\n"
    "rim.rotation_euler=d2.to_track_quat('-Z','Y').to_euler()\n"

    # Piano (tavolo bianco caldo)
    "bpy.ops.mesh.primitive_plane_add(size=1.5, location=(0,0,-0.001))\n"
    "pl=bpy.context.active_object; pl.name='Table'\n"
    "mt=bpy.data.materials.new('TableMat'); mt.use_nodes=True\n"
    "mt.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(0.88,0.85,0.80,1.0)\n"
    "mt.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=0.7\n"
    "pl.data.materials.append(mt)\n"

    # World: grigio-blu scuro elegante
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.06,0.07,0.09,1.0)\n"
    "bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.3\n"
    "result={'cam':cam.name}\n",
    timeout=15
)
print("  Scene:", r)

# ─── STEP 6: render ────────────────────────────────────────────────────────
print("Step 6: render v1...")
render_save("D:/blender-claude/renders/espresso_v1.png", w=1280, h=960, exposure=0.0)
print("Done.")
