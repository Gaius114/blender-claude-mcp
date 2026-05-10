# Blender Claude MCP Connector

A lightweight, reliable bridge that lets **Claude Code control Blender** via a local HTTP server — no external dependencies, no timeouts.

```
Claude Code
    │  stdio JSON-RPC (MCP protocol)
    ▼
blender_mcp_http.py        ← MCP bridge (pure Python stdlib)
    │  HTTP POST localhost:7234
    ▼
claude_blender_addon.py    ← Blender addon (HTTP server) v3.0
    │  bpy.app.timers → main thread
    ▼
Blender Python API (bpy)
```

Everything runs **100% locally** — no cloud, no API keys beyond Claude Code itself.

---

## Features

- ✅ Execute arbitrary Python (`bpy` + `bmesh`) code in Blender from Claude
- ✅ EEVEE render → base64 PNG response (visual loop)
- ✅ Full Geometry Nodes access
- ✅ UI panel in Blender (Properties → Scene → Claude MCP)
- ✅ Thread-safe via `bpy.app.timers` + `queue.Queue`
- ✅ Zero external Python dependencies (stdlib only)
- ✅ Compatible with Blender 4.x and 5.x

---

## Contents

| Path | Description |
|------|-------------|
| `addon/claude_blender_addon.py` | Blender addon v3.0 — HTTP server on port 7234 |
| `skill/SKILL.md` | Claude Code skill — modeling helpers, materials, camera presets |
| `scripts/` | Example scripts: donut, wine bottle, house, GeoNodes fixes |

---

## Installation

### 1 — Blender Addon

1. Download [`addon/claude_blender_addon.py`](addon/claude_blender_addon.py)
2. In Blender: `Edit > Preferences > Add-ons > Install`
3. Select the file → enable the checkbox ✓
4. The server starts automatically on `localhost:7234`
5. Verify: `Properties > Scene > Claude MCP` shows **● Attivo**

> If the server doesn't auto-start, open the Scripting tab and run:
> ```python
> import bpy
> bpy.ops.claude.start_server()
> ```

### 2 — Claude Code Skill

Copy the skill to your Claude skills folder:
```
~/.claude/skills/blender-arch/SKILL.md
```

Then invoke it in Claude Code with:
```
/blender-arch build a donut with pink icing and sprinkles
```

### 3 — MCP Bridge (optional)

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "python",
      "args": ["-u", "/path/to/blender_mcp_http.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "BLENDER_URL": "http://localhost:7234"
      }
    }
  }
}
```

---

## HTTP API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/ping` | Health check, returns Blender version |
| `GET`  | `/scene_info` | Objects, materials, camera, render settings |
| `GET`  | `/screenshot` | Viewport screenshot (base64 PNG) |
| `POST` | `/execute` | Execute Python code in Blender |
| `POST` | `/render` | Render scene and save to file |

### `/execute` body

```json
{
  "code": "result = [o.name for o in bpy.data.objects]",
  "timeout": 60
}
```

Assign any JSON-serialisable value to `result` to get data back.

---

## Skill Capabilities (v3.0)

The `skill/SKILL.md` provides Claude with ready-made helpers for:

**Modeling**
- Box, cylinder, sphere, plane helpers
- bmesh extrude, pipe/curve along points, lathe (revolution via `bpy.ops.mesh.spin`)
- Modifiers: Bevel, SubSurf, Solidify, Array, Mirror, Boolean

**Architecture**
- Walls with Boolean openings, window frames, railings, staircases, hip roofs

**Materials** — Blender 5.x accurate (OpenPBR)
- `mat_pbr`, `mat_noise` (with `noise_type` variants), `mat_glass`
- `mat_metal` with Coat/clearcoat layer
- `mat_subsurface` — SSS for skin, wax, marble (RANDOM_WALK / RANDOM_WALK_SKIN)
- `mat_fabric` — Sheen layer for velvet, linen, cotton
- `mat_wood`, `mat_blueprint`
- All use `surface_render_method` (replaces deprecated `blend_method`)

**Camera & Lighting**
- 8 camera presets (product, isometric, street level, interior...)
- 3-point lighting, architectural sun+fill

---

## Visual Loop

Claude's core workflow — execute → render → analyze → iterate:

```python
def blender(code, timeout=60):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req  = urllib.request.Request("http://localhost:7234/execute", data=data,
                                  headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout+10).read())
    return r.get("ok")

# Build → render → Read PNG → analyze → fix → repeat
blender(build_code)
render_and_read("preview.png")  # → Read tool → visual analysis
blender(fix_code)               # → iterate until satisfied
```

---

## Architecture Notes

### Thread Safety

Blender's Python API (`bpy`) **must** be called from the main thread. The addon handles this with:

```python
def run_in_main(code, timeout=30.0):
    done = threading.Event()
    def _run():
        exec(code, namespace)
        done.set()
        return None  # don't repeat timer
    bpy.app.timers.register(_run, first_interval=0.0)
    done.wait(timeout=timeout)
```

### Why HTTP over raw sockets?

| | Raw TCP socket | HTTP (this project) |
|-|----------------|---------------------|
| Request framing | Manual | Built-in |
| Timeouts | Manual | Native |
| Debugging | Hard | `curl` |
| Reconnection | Manual | Automatic |

---

## Requirements

- Blender 4.0+ (tested on 5.1)
- Python 3.8+ for the bridge (stdlib only)
- Claude Code

## License

MIT

## Contributing

PRs welcome! Ideas:
- [ ] WebSocket support for real-time updates
- [ ] Authentication token for the HTTP server
- [ ] Blender Extension Marketplace packaging (`blender_manifest.toml`)
- [ ] Auto-reconnect in the bridge
