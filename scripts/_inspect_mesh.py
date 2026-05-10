import urllib.request, json

BLENDER_URL = "http://localhost:7234"
def blender(code, timeout=30):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r    = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    if "error" in r: print("ERR:", r["error"][:800]); return None
    return r.get("ok")

code = """
import bpy

def mesh_info(name):
    ob = bpy.data.objects.get(name)
    if not ob:
        return None
    me = ob.data
    # Check for custom split normals
    has_custom = me.has_custom_normals
    # Check smooth flags (use_smooth per polygon)
    smooth_flags = list(set(p.use_smooth for p in me.polygons))
    # Check loops normals (split normals per loop)
    me.calc_normals_split()
    loop0_n = list(me.loops[0].normal)
    loop1_n = list(me.loops[1].normal)
    loop2_n = list(me.loops[2].normal)
    loop3_n = list(me.loops[3].normal)
    return {
        "has_custom": has_custom,
        "smooth": smooth_flags,
        "l0n": loop0_n,
        "l1n": loop1_n,
        "l2n": loop2_n,
        "l3n": loop3_n,
        "polys": len(me.polygons)
    }

result = {
    "prim": mesh_info("PrimCone"),
    "bmesh": mesh_info("BmeshCone")
}
"""

r = blender(code, timeout=15)
if r:
    print("Primitive cone:")
    p = r["prim"]
    print(f"  has_custom_normals: {p['has_custom']}")
    print(f"  smooth flags: {p['smooth']}")
    print(f"  loop normals:")
    for k in ['l0n','l1n','l2n','l3n']:
        print(f"    {k}: {[round(x,4) for x in p[k]]}")
    print()
    print("Bmesh cone:")
    b = r["bmesh"]
    print(f"  has_custom_normals: {b['has_custom']}")
    print(f"  smooth flags: {b['smooth']}")
    print(f"  loop normals:")
    for k in ['l0n','l1n','l2n','l3n']:
        print(f"    {k}: {[round(x,4) for x in b[k]]}")
