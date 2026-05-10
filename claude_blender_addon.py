"""
Claude MCP Connector — Addon Blender
=====================================
Installa in Blender: Edit > Preferences > Add-ons > Install > seleziona questo file.
Attiva l'addon → avvia automaticamente un server HTTP su localhost:7234.
Claude Code si connette a questo server via il bridge MCP (blender_mcp_http.py).

Architettura:
  Claude Code ←(stdio JSON-RPC)→ blender_mcp_http.py ←(HTTP)→ questo addon ←(bpy)→ Blender
"""

bl_info = {
    "name":        "Claude MCP Connector",
    "author":      "Claude Code",
    "version":     (2, 0, 0),
    "blender":     (4, 0, 0),
    "location":    "Properties > Scene > Claude MCP",
    "description": "Server HTTP locale che permette a Claude Code di controllare Blender",
    "category":    "Development",
}

import bpy
import threading
import queue
import json
import traceback
import base64
import tempfile
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── CONFIGURAZIONE ─────────────────────────────────────────────────────────
PORT    = 7234
HOST    = "localhost"

# ── STATO GLOBALE ──────────────────────────────────────────────────────────
_server        = None
_server_thread = None

# ── ESECUZIONE THREAD-SAFE NEL MAIN THREAD ────────────────────────────────
def run_in_main(code: str, timeout: float = 30.0) -> dict:
    """
    Invia il codice al main thread di Blender tramite bpy.app.timers.
    bpy.app.timers.register() è thread-safe: può essere chiamato da thread secondari.
    Il main thread esegue il codice e segnala il risultato tramite threading.Event.
    """
    result   = {}
    done     = threading.Event()

    def _run():
        try:
            namespace = {
                "bpy":    bpy,
                "bmesh":  __import__("bmesh"),
                "math":   __import__("math"),
                "Vector": __import__("mathutils").Vector,
                "result": None,
            }
            exec(compile(code, "<claude>", "exec"), namespace)
            result["ok"] = namespace.get("result", "eseguito")
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            done.set()
        return None  # None = non ripetere il timer

    bpy.app.timers.register(_run, first_interval=0.0)
    timed_out = not done.wait(timeout=timeout)
    if timed_out:
        result["error"] = f"Timeout ({timeout}s): Blender non ha risposto"
    return result

# ── HTTP HANDLER ──────────────────────────────────────────────────────────
class ClaudeHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silenzia i log HTTP nel terminale di Blender

    def _send(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ── GET endpoints ──────────────────────────────────────────────────────
    def do_GET(self):
        if self.path == "/ping":
            self._send({"status": "ok",
                         "blender": bpy.app.version_string,
                         "port":    PORT})

        elif self.path == "/scene_info":
            r = run_in_main("""
result = {
    "objects":  [{"name": o.name, "type": o.type,
                  "location": [round(v,3) for v in o.location],
                  "visible":  o.visible_get()}
                 for o in bpy.data.objects],
    "materials": [m.name for m in bpy.data.materials],
    "camera":    bpy.context.scene.camera.name if bpy.context.scene.camera else None,
    "frame":     bpy.context.scene.frame_current,
    "engine":    bpy.context.scene.render.engine,
    "resolution":(bpy.context.scene.render.resolution_x,
                  bpy.context.scene.render.resolution_y),
}
""")
            self._send(r)

        elif self.path == "/screenshot":
            # Salva viewport come PNG in temp, legge i bytes, li codifica in base64
            tmp = tempfile.mktemp(suffix=".png")
            code = f"""
import bpy
bpy.ops.screen.screenshot(filepath=r'{tmp}', full=False)
result = r'{tmp}'
"""
            r = run_in_main(code)
            if "error" in r:
                self._send(r, 500)
            else:
                try:
                    with open(tmp, "rb") as f:
                        data = base64.b64encode(f.read()).decode()
                    os.remove(tmp)
                    self._send({"image_base64": data, "format": "png"})
                except Exception as e:
                    self._send({"error": str(e)}, 500)
        else:
            self._send({"error": "endpoint non trovato"}, 404)

    # ── POST endpoints ─────────────────────────────────────────────────────
    def do_POST(self):
        body = self._read_body()
        if body is None:
            self._send({"error": "JSON non valido"}, 400)
            return

        if self.path == "/execute":
            code = body.get("code", "").strip()
            if not code:
                self._send({"error": "campo 'code' mancante"}, 400)
                return
            r = run_in_main(code)
            self._send(r, 500 if "error" in r else 200)

        elif self.path == "/render":
            # Renderizza e salva in un path (opzionale), ritorna il path
            filepath = body.get("filepath", "//render_claude.png")
            code = f"""
import bpy
bpy.context.scene.render.filepath = r'{filepath}'
bpy.ops.render.render(write_still=True)
result = bpy.context.scene.render.filepath
"""
            r = run_in_main(code, timeout=300.0)  # render può durare minuti
            self._send(r, 500 if "error" in r else 200)

        else:
            self._send({"error": "endpoint non trovato"}, 404)


# ── OPERATORI BLENDER ─────────────────────────────────────────────────────
class CLAUDE_OT_StartServer(bpy.types.Operator):
    bl_idname = "claude.start_server"
    bl_label  = "Avvia Server Claude"
    bl_description = f"Avvia il server HTTP su localhost:{PORT}"

    def execute(self, context):
        global _server, _server_thread
        if _server is not None:
            self.report({"WARNING"}, "Server già in esecuzione")
            return {"CANCELLED"}
        try:
            _server = HTTPServer((HOST, PORT), ClaudeHandler)
            _server.timeout = 1.0
            _server_thread = threading.Thread(
                target=_server.serve_forever,
                daemon=True,
                name="ClaudeMCP-HTTP"
            )
            _server_thread.start()
            self.report({"INFO"}, f"✅ Claude server avviato → localhost:{PORT}")
        except OSError as e:
            self.report({"ERROR"}, f"Porta {PORT} già in uso: {e}")
            return {"CANCELLED"}
        return {"FINISHED"}


class CLAUDE_OT_StopServer(bpy.types.Operator):
    bl_idname  = "claude.stop_server"
    bl_label   = "Ferma Server Claude"
    bl_description = "Ferma il server HTTP"

    def execute(self, context):
        global _server, _server_thread
        if _server is None:
            self.report({"WARNING"}, "Server non in esecuzione")
            return {"CANCELLED"}
        _server.shutdown()
        _server = None
        _server_thread = None
        self.report({"INFO"}, "Server Claude fermato")
        return {"FINISHED"}


# ── PANNELLO UI ───────────────────────────────────────────────────────────
class CLAUDE_PT_Panel(bpy.types.Panel):
    bl_label      = "Claude MCP"
    bl_idname     = "CLAUDE_PT_panel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context    = "scene"

    def draw(self, context):
        layout = self.layout
        global _server
        running = _server is not None

        row = layout.row()
        row.scale_y = 1.4
        if running:
            row.operator("claude.stop_server", icon="CANCEL",  text="Ferma Server")
        else:
            row.operator("claude.start_server", icon="PLAY",   text="Avvia Server")

        box = layout.box()
        if running:
            box.label(text=f"● Attivo  →  localhost:{PORT}", icon="CHECKMARK")
            box.label(text="Claude Code può controllare Blender", icon="LINKED")
        else:
            box.label(text="○ Server fermo",  icon="X")
            box.label(text="Premi Avvia per connetterti", icon="INFO")

        layout.separator()
        layout.label(text="Endpoints disponibili:", icon="WORLD")
        for ep in ["GET  /ping", "GET  /scene_info", "GET  /screenshot",
                   "POST /execute", "POST /render"]:
            layout.label(text=ep, icon="DOT")


# ── REGISTRAZIONE ─────────────────────────────────────────────────────────
_classes = [CLAUDE_OT_StartServer, CLAUDE_OT_StopServer, CLAUDE_PT_Panel]


def _auto_start():
    """Avvio automatico dopo 1 secondo dall'attivazione dell'addon."""
    if _server is None:
        bpy.ops.claude.start_server()
    return None  # non ripetere


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_auto_start, first_interval=1.0)


def unregister():
    global _server
    if _server:
        _server.shutdown()
        _server = None
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
