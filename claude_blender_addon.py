"""
Claude MCP Connector v3.0 — Addon Blender
==========================================
Server HTTP locale con pipeline step-by-step, visual loop e accesso
a tutti i principali tool di Blender: Modeling, Shading, Geometry Nodes,
UV Editing, Texture Paint, Compositing, Sculpting.

Installa: Edit > Preferences > Add-ons > Install > questo file
"""

bl_info = {
    "name":        "Claude MCP Connector",
    "author":      "Claude Code",
    "version":     (3, 0, 0),
    "blender":     (4, 0, 0),
    "location":    "Properties > Scene > Claude MCP",
    "description": "Pipeline AI step-by-step: Modeling → Shading → GeoNodes → Compositing",
    "category":    "Development",
}

import bpy, threading, queue, json, traceback, base64, tempfile, os, math
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8765

_server        = None
_server_thread = None

# ── ESECUZIONE THREAD-SAFE ────────────────────────────────────────────────
def run_in_main(code: str, timeout: float = 60.0) -> dict:
    result = {}
    done   = threading.Event()
    def _run():
        try:
            ns = {
                "bpy": bpy, "math": math,
                "bmesh": __import__("bmesh"),
                "Vector": __import__("mathutils").Vector,
                "Matrix": __import__("mathutils").Matrix,
                "result": None,
            }
            exec(compile(code, "<claude>", "exec"), ns)
            result["ok"] = ns.get("result", "done")
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            done.set()
        return None
    bpy.app.timers.register(_run, first_interval=0.0)
    if not done.wait(timeout=timeout):
        result["error"] = f"Timeout ({timeout}s)"
    return result

# ── HTTP HANDLER ──────────────────────────────────────────────────────────
class ClaudeHandler(BaseHTTPRequestHandler):

    def log_message(self, *a): pass

    def _send(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        try: return json.loads(self.rfile.read(n))
        except: return {}

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):

        if self.path == "/ping":
            self._send({"status": "ok", "blender": bpy.app.version_string,
                        "version": "3.0", "port": PORT})

        elif self.path == "/scene_info":
            r = run_in_main("""
result = {
    "objects":   [{"name": o.name, "type": o.type,
                   "location": [round(v,3) for v in o.location],
                   "dimensions": [round(v,3) for v in o.dimensions]}
                  for o in bpy.data.objects],
    "materials": [m.name for m in bpy.data.materials],
    "camera":    bpy.context.scene.camera.name if bpy.context.scene.camera else None,
    "engine":    bpy.context.scene.render.engine,
    "frame":     bpy.context.scene.frame_current,
    "collections": [c.name for c in bpy.data.collections],
}
""")
            self._send(r)

        elif self.path == "/screenshot":
            tmp = tempfile.mktemp(suffix=".png")
            r = run_in_main(f"""
import bpy, base64
bpy.ops.screen.screenshot(filepath=r'{tmp}', full=False)
with open(r'{tmp}', 'rb') as f:
    result = base64.b64encode(f.read()).decode()
""")
            if "error" in r: self._send(r, 500)
            else: self._send({"image_base64": r.get("ok",""), "format":"png"})

        else:
            self._send({"error": "Not found"}, 404)

    # ── POST ──────────────────────────────────────────────────────────────
    def do_POST(self):
        body = self._body()

        # ── Esecuzione codice generico ────────────────────────────────────
        if self.path == "/execute":
            code = body.get("code","").strip()
            if not code:
                self._send({"error": "campo 'code' vuoto"}, 400); return
            r = run_in_main(code, timeout=body.get("timeout", 60))
            self._send(r, 500 if "error" in r else 200)

        # ── Render preview veloce (EEVEE) ─────────────────────────────────
        elif self.path == "/render_preview":
            w   = body.get("width",  960)
            h   = body.get("height", 540)
            tmp = tempfile.mktemp(suffix=".png").replace("\\", "/")
            r   = run_in_main(f"""
import bpy, base64, os
sc = bpy.context.scene
_eng = sc.render.engine
_rx, _ry = sc.render.resolution_x, sc.render.resolution_y
_path = sc.render.filepath
_samples = sc.cycles.samples

# Usa EEVEE per preview veloce
engines = {{e.bl_idname for e in bpy.types.RenderEngine.__subclasses__()}}
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
sc.render.resolution_x = {w}
sc.render.resolution_y = {h}
sc.render.filepath = r'{tmp}'
sc.render.image_settings.file_format = 'PNG'

try:
    bpy.ops.render.render(write_still=True)
    with open(r'{tmp}', 'rb') as f:
        _img = base64.b64encode(f.read()).decode()
    os.remove(r'{tmp}')
    result = {{"image": _img}}
except Exception as e:
    result = {{"error": str(e)}}
finally:
    sc.render.engine = _eng
    sc.render.resolution_x = _rx
    sc.render.resolution_y = _ry
    sc.render.filepath = _path
    sc.cycles.samples = _samples
""", timeout=120)
            if "error" in r: self._send(r, 500)
            elif isinstance(r.get("ok"), dict) and "error" in r["ok"]:
                self._send({"error": r["ok"]["error"]}, 500)
            else:
                img = (r.get("ok") or {}).get("image", "")
                self._send({"image_base64": img, "format": "png"})

        # ── Shading: nodo materiale completo ──────────────────────────────
        elif self.path == "/apply_shader":
            obj_name  = body.get("object")
            mat_name  = body.get("material_name", "ClaudeMat")
            node_code = body.get("node_code", "")  # codice Python che costruisce i nodi
            r = run_in_main(f"""
import bpy
obj = bpy.data.objects.get("{obj_name}")
if not obj:
    result = {{"error": "Oggetto '{obj_name}' non trovato"}}
else:
    # Crea o recupera materiale
    mat = bpy.data.materials.get("{mat_name}") or bpy.data.materials.new("{mat_name}")
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    # Esegui il codice dei nodi con 'mat' disponibile nel namespace
    {node_code}
    # Assegna all'oggetto
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    result = {{"ok": "Shader '{mat_name}' applicato a '{obj_name}'"}}
""")
            self._send(r, 500 if "error" in r else 200)

        # ── Geometry Nodes ────────────────────────────────────────────────
        elif self.path == "/geometry_nodes":
            obj_name  = body.get("object")
            mod_name  = body.get("modifier_name", "GeoNodes_Claude")
            node_code = body.get("node_code", "")  # costruisce il node group
            r = run_in_main(f"""
import bpy
obj = bpy.data.objects.get("{obj_name}")
if not obj:
    result = {{"error": "Oggetto '{obj_name}' non trovato"}}
else:
    # Rimuovi modifier esistente con stesso nome
    existing = obj.modifiers.get("{mod_name}")
    if existing: obj.modifiers.remove(existing)
    mod = obj.modifiers.new("{mod_name}", "NODES")
    # Esegui node_code con 'mod' e 'obj' disponibili
    {node_code}
    result = {{"ok": "Geometry nodes '{mod_name}' applicato a '{obj_name}'"}}
""", timeout=30)
            self._send(r, 500 if "error" in r else 200)

        # ── Applica modifier standard ──────────────────────────────────────
        elif self.path == "/apply_modifier":
            obj_name = body.get("object")
            mod_type = body.get("type", "SUBSURF")   # SUBSURF, BEVEL, SOLIDIFY, ARRAY, MIRROR...
            params   = body.get("params", {})
            r = run_in_main(f"""
import bpy
obj = bpy.data.objects.get("{obj_name}")
if not obj:
    result = {{"error": "Oggetto '{obj_name}' non trovato"}}
else:
    mod = obj.modifiers.new(name="{mod_type}", type="{mod_type}")
    params = {json.dumps(params)}
    for k, v in params.items():
        try: setattr(mod, k, v)
        except: pass
    result = {{"ok": f"Modifier {mod_type} aggiunto a {obj_name}", "params": params}}
""")
            self._send(r, 500 if "error" in r else 200)

        # ── UV Unwrap ──────────────────────────────────────────────────────
        elif self.path == "/unwrap_uv":
            obj_name = body.get("object")
            method   = body.get("method", "SMART_PROJECT")  # SMART_PROJECT, UNWRAP, CUBE_PROJECT
            r = run_in_main(f"""
import bpy
obj = bpy.data.objects.get("{obj_name}")
if not obj:
    result = {{"error": "Oggetto '{obj_name}' non trovato"}}
else:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    if "{method}" == "SMART_PROJECT":
        bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.02)
    elif "{method}" == "UNWRAP":
        bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.02)
    elif "{method}" == "CUBE_PROJECT":
        bpy.ops.uv.cube_project(scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    result = {{"ok": f"UV {method} applicato a {obj_name}"}}
""")
            self._send(r, 500 if "error" in r else 200)

        # ── Setup Compositing ─────────────────────────────────────────────
        elif self.path == "/setup_compositor":
            cfg = body  # bloom, color_grade, fog, vignette, sharpen
            r = run_in_main(f"""
import bpy
sc = bpy.context.scene
sc.use_nodes = True
tree = sc.node_tree
tree.nodes.clear()

cfg = {json.dumps(cfg)}

# Nodi base
rl  = tree.nodes.new('CompositorNodeRLayers'); rl.location = (-400,0)
out = tree.nodes.new('CompositorNodeComposite'); out.location = (800,0)

current = rl.outputs['Image']

# ── Glare / Bloom ──────────────────────────────────────────────────────
if cfg.get('bloom', True):
    glare = tree.nodes.new('CompositorNodeGlare')
    glare.location = (-100, 100)
    glare.glare_type = 'BLOOM'
    glare.threshold = cfg.get('bloom_threshold', 0.8)
    glare.size = cfg.get('bloom_size', 7)
    glare.mix  = cfg.get('bloom_mix', 0.08)
    tree.links.new(current, glare.inputs['Image'])
    current = glare.outputs['Image']

# ── Color Balance (color grade) ────────────────────────────────────────
if cfg.get('color_grade', True):
    cb = tree.nodes.new('CompositorNodeColorBalance')
    cb.location = (200, 100)
    cb.correction_method = 'LIFT_GAMMA_GAIN'
    cb.lift  = cfg.get('lift',  (1.02, 1.00, 0.98, 1.0))
    cb.gamma = cfg.get('gamma', (0.98, 1.00, 1.02, 1.0))
    cb.gain  = cfg.get('gain',  (1.00, 1.00, 1.00, 1.0))
    tree.links.new(current, cb.inputs['Image'])
    current = cb.outputs['Image']

# ── Lens Distortion / Vignette ─────────────────────────────────────────
if cfg.get('vignette', True):
    ld = tree.nodes.new('CompositorNodeLensdist')
    ld.location = (400, 100)
    ld.inputs['Distort'].default_value  = cfg.get('distort',  -0.02)
    ld.inputs['Dispersion'].default_value = cfg.get('dispersion', 0.01)
    tree.links.new(current, ld.inputs['Image'])
    current = ld.outputs['Image']

# ── Sharpen (filter) ───────────────────────────────────────────────────
if cfg.get('sharpen', False):
    flt = tree.nodes.new('CompositorNodeFilter')
    flt.location = (600, 100)
    flt.filter_type = 'SHARPEN'
    flt.inputs['Fac'].default_value = cfg.get('sharpen_fac', 0.3)
    tree.links.new(current, flt.inputs['Image'])
    current = flt.outputs['Image']

# ── Output ─────────────────────────────────────────────────────────────
tree.links.new(current, out.inputs['Image'])
result = {{"ok": "Compositor configurato", "nodes": [n.name for n in tree.nodes]}}
""")
            self._send(r, 500 if "error" in r else 200)

        # ── Render finale (Cycles, alta qualità) ──────────────────────────
        elif self.path == "/render":
            filepath = body.get("filepath", "//render_claude.png")
            samples  = body.get("samples", 256)
            r = run_in_main(f"""
import bpy
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = {samples}
sc.cycles.use_denoising = True
sc.render.filepath = r'{filepath}'
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
result = sc.render.filepath
""", timeout=600)
            self._send(r, 500 if "error" in r else 200)

        else:
            self._send({"error": "Not found"}, 404)


# ── OPERATORI & UI ────────────────────────────────────────────────────────
class CLAUDE_OT_StartServer(bpy.types.Operator):
    bl_idname = "claude.start_server"
    bl_label  = "Avvia Server Claude"
    def execute(self, context):
        global _server, _server_thread
        if _server: self.report({"WARNING"},"Server già attivo"); return {"CANCELLED"}
        try:
            _server = HTTPServer(("localhost", PORT), ClaudeHandler)
            _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
            _server_thread.start()
            self.report({"INFO"}, f"✅ Claude MCP v3.0 → localhost:{PORT}")
        except OSError as e:
            self.report({"ERROR"}, f"Porta {PORT} occupata: {e}"); return {"CANCELLED"}
        return {"FINISHED"}

class CLAUDE_OT_StopServer(bpy.types.Operator):
    bl_idname = "claude.stop_server"
    bl_label  = "Ferma Server"
    def execute(self, context):
        global _server, _server_thread
        if not _server: self.report({"WARNING"},"Non attivo"); return {"CANCELLED"}
        _server.shutdown(); _server = None; _server_thread = None
        self.report({"INFO"},"Server fermato"); return {"FINISHED"}

class CLAUDE_PT_Panel(bpy.types.Panel):
    bl_label       = "Claude MCP"
    bl_idname      = "CLAUDE_PT_panel"
    bl_space_type  = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context     = "scene"

    def draw(self, context):
        layout = self.layout
        running = _server is not None
        row = layout.row(); row.scale_y = 1.4
        if running: row.operator("claude.stop_server", icon="CANCEL", text="Ferma Server")
        else:       row.operator("claude.start_server", icon="PLAY",  text="Avvia Server")
        box = layout.box()
        if running:
            box.label(text=f"● v3.0  →  localhost:{PORT}", icon="CHECKMARK")
            box.label(text="Modeling · Shading · GeoNodes", icon="LINKED")
            box.label(text="UV · Compositing · Visual Loop", icon="LINKED")
        else:
            box.label(text="○ Server fermo", icon="X")
        layout.separator()
        layout.label(text="Endpoints:", icon="WORLD")
        for ep in ["GET  /ping  /scene_info  /screenshot",
                   "POST /execute  /render_preview",
                   "POST /apply_shader  /geometry_nodes",
                   "POST /apply_modifier  /unwrap_uv",
                   "POST /setup_compositor  /render"]:
            layout.label(text=ep, icon="DOT")

_classes = [CLAUDE_OT_StartServer, CLAUDE_OT_StopServer, CLAUDE_PT_Panel]

def _auto_start():
    if _server is None: bpy.ops.claude.start_server()
    return None

def register():
    for cls in _classes: bpy.utils.register_class(cls)
    bpy.app.timers.register(_auto_start, first_interval=1.0)

def unregister():
    global _server
    if _server: _server.shutdown(); _server = None
    for cls in reversed(_classes): bpy.utils.unregister_class(cls)
