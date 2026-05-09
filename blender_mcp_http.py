#!/usr/bin/env python3
"""
Claude Code ↔ Blender MCP Bridge (HTTP)
=========================================
Sostituisce blender_bridge.py — usa HTTP invece di socket raw.
Nessuna dipendenza esterna: solo stdlib Python.

Flusso:
  Claude Code
      │ stdio JSON-RPC (MCP protocol)
      ▼
  questo script (bridge)
      │ HTTP POST/GET a localhost:7234
      ▼
  claude_blender_addon.py (dentro Blender)
      │ bpy.app.timers → main thread
      ▼
  Blender Python API (bpy)
"""

import sys
import json
import urllib.request
import urllib.error
import os

BLENDER_URL = os.getenv("BLENDER_URL", "http://localhost:7234")
TIMEOUT     = 60  # secondi (aumenta per render lunghi)

def log(msg: str):
    print(f"[blender-mcp] {msg}", file=sys.stderr, flush=True)

# ── HTTP HELPERS ──────────────────────────────────────────────────────────
def http_get(path: str):
    try:
        with urllib.request.urlopen(f"{BLENDER_URL}{path}", timeout=TIMEOUT) as r:
            return json.loads(r.read()), None
    except urllib.error.URLError as e:
        return None, f"Blender non raggiungibile ({e}). Addon attivo in Blender?"
    except Exception as e:
        return None, str(e)

def http_post(path: str, data: dict):
    try:
        body = json.dumps(data).encode("utf-8")
        req  = urllib.request.Request(
            f"{BLENDER_URL}{path}",
            data    = body,
            headers = {"Content-Type": "application/json"},
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read()), None
    except urllib.error.URLError as e:
        return None, f"Blender non raggiungibile ({e}). Addon attivo in Blender?"
    except Exception as e:
        return None, str(e)

# ── TOOL DEFINITIONS ──────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "execute_blender_code",
        "description": (
            "Esegue codice Python direttamente in Blender (bpy disponibile). "
            "Assegna un valore JSON-serializzabile a 'result' per ricevere dati. "
            "Esempi: creare oggetti, modificare materiali, spostare camera, ecc."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Codice Python da eseguire in Blender"
                }
            },
            "required": ["code"]
        }
    },
    {
        "name": "get_scene_info",
        "description": "Restituisce la lista di oggetti, materiali, camera e impostazioni render della scena Blender corrente.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "ping_blender",
        "description": "Verifica la connessione con Blender. Ritorna la versione di Blender se connesso.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_screenshot",
        "description": "Cattura uno screenshot del viewport Blender e lo restituisce come immagine base64 PNG.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "render_scene",
        "description": "Avvia il render della scena Blender e salva il risultato. Può impiegare diversi minuti.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Percorso output del render (default: //render_claude.png)"
                }
            }
        }
    }
]

# ── TOOL HANDLERS ─────────────────────────────────────────────────────────
def handle_tool(name: str, args: dict) -> str:

    if name == "ping_blender":
        result, err = http_get("/ping")
        if err:
            return f"❌ {err}"
        return f"✅ Blender {result.get('blender', '?')} connesso su porta {result.get('port', '?')}"

    elif name == "get_scene_info":
        result, err = http_get("/scene_info")
        if err:
            return f"Errore: {err}"
        return json.dumps(result, indent=2, ensure_ascii=False)

    elif name == "execute_blender_code":
        code = args.get("code", "").strip()
        if not code:
            return "Errore: campo 'code' vuoto"
        result, err = http_post("/execute", {"code": code})
        if err:
            return f"Errore: {err}"
        if result is None:
            return "Errore: risposta vuota da Blender"
        if "error" in result:
            return f"Errore Blender:\n{result['error']}"
        val = result.get("ok", "eseguito")
        if isinstance(val, (dict, list)):
            return json.dumps(val, indent=2, ensure_ascii=False)
        return str(val)

    elif name == "get_screenshot":
        result, err = http_get("/screenshot")
        if err:
            return f"Errore: {err}"
        if "error" in result:
            return f"Errore screenshot: {result['error']}"
        # Restituisce base64 — Claude lo visualizza come immagine
        b64 = result.get("image_base64", "")
        return f"data:image/png;base64,{b64}" if b64 else "Nessuna immagine ricevuta"

    elif name == "render_scene":
        filepath = args.get("filepath", "//render_claude.png")
        log(f"Avvio render → {filepath} (potrebbe richiedere minuti...)")
        result, err = http_post("/render", {"filepath": filepath})
        if err:
            return f"Errore: {err}"
        if result and "error" in result:
            return f"Errore render: {result['error']}"
        saved = result.get("ok", filepath) if result else filepath
        return f"✅ Render completato → {saved}"

    return f"Tool sconosciuto: {name}"

# ── MCP STDIO SERVER ──────────────────────────────────────────────────────
def send(msg: dict):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def main():
    log("Blender HTTP-MCP bridge v2.0 avviato")
    log(f"Blender URL: {BLENDER_URL}")

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                log(f"JSON parse error: {e}")
                continue

            msg_id = msg.get("id")
            method  = msg.get("method", "")
            params  = msg.get("params", {})

            log(f"← {method} (id={msg_id})")

            if method == "initialize":
                send({
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities":    {"tools": {}},
                        "serverInfo":      {"name": "Blender-HTTP-MCP", "version": "2.0"}
                    }
                })

            elif method in ("notifications/initialized", "initialized"):
                pass  # nessuna risposta necessaria

            elif method == "tools/list":
                send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                log(f"  → tool: {tool_name}")
                text = handle_tool(tool_name, tool_args)
                send({
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": text}]}
                })

            elif method == "ping":
                send({"jsonrpc": "2.0", "id": msg_id, "result": {}})

            else:
                log(f"Metodo sconosciuto: {method}")
                if msg_id is not None:
                    send({
                        "jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32601,
                                  "message": f"Method not found: {method}"}
                    })

        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Errore loop: {e}")

    log("Bridge terminato")

if __name__ == "__main__":
    main()
