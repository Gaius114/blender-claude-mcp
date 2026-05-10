import urllib.request, json, base64

BLENDER_URL = "http://localhost:7234"

def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout + 10)
    r    = json.loads(resp.read().decode())
    if "error" in r: print("  ERR:", r["error"][:500]); return None
    return r.get("ok")

def render_save(path, w=1920, h=1080, exposure=0.08):
    code = f"""
import bpy, base64, os, tempfile
sc = bpy.context.scene
try: sc.render.engine = "BLENDER_EEVEE_NEXT"
except: sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x={w}; sc.render.resolution_y={h}
sc.view_settings.view_transform="Filmic"
sc.view_settings.look="Medium High Contrast"
sc.view_settings.exposure={exposure}
sc.render.use_compositing=False
tmp=tempfile.mktemp(suffix=".png"); sc.render.filepath=tmp
bpy.ops.render.render(write_still=True)
with open(tmp,"rb") as f: b64=base64.b64encode(f.read()).decode()
os.remove(tmp)
result={{"b64":b64}}
"""
    r = blender(code, timeout=180)
    if r and "b64" in r:
        img = base64.b64decode(r["b64"])
        with open(path, "wb") as f: f.write(img)
        print(f"  Saved: {path} ({len(img)//1024}KB)")

# Fix GeoNodes: aggiungi Join Geometry per tenere sia icing che sprinkles
r = blender("""
import bpy

icing = bpy.data.objects.get("Icing")
if not icing:
    result = {"error": "Icing not found"}
else:
    # Trova il node group degli sprinkles
    ng = bpy.data.node_groups.get("SprinkleScatter")
    if ng:
        nodes = ng.nodes; links = ng.links

        # Trova nodi esistenti
        in_node  = next((n for n in nodes if n.bl_idname == "NodeGroupInput"),  None)
        out_node = next((n for n in nodes if n.bl_idname == "NodeGroupOutput"), None)
        realize  = next((n for n in nodes if n.bl_idname == "GeometryNodeRealizeInstances"), None)

        if in_node and out_node and realize:
            # Disconnetti realize dall'output
            for link in list(links):
                if link.to_node == out_node:
                    links.remove(link)

            # Aggiungi Join Geometry
            join = nodes.new("GeometryNodeJoinGeometry")
            join.location = (realize.location.x + 200, realize.location.y)

            # Collega: icing mesh + sprinkles instances → join → output
            links.new(in_node.outputs[0],          join.inputs["Geometry"])
            links.new(realize.outputs["Geometry"], join.inputs["Geometry"])
            links.new(join.outputs["Geometry"],    out_node.inputs[0])

    result = {
        "gn_nodes": len(ng.nodes) if ng else 0,
        "gn_links": len(ng.links) if ng else 0,
        "fix": "join_geometry_added"
    }
""", timeout=10)
print("GeoNodes fix:", r)

print("Rendering con icing rosa + sprinkles...")
render_save("D:/blender-claude/renders/donut_FINAL2.png", w=1920, h=1080, exposure=0.08)
