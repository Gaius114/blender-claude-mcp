# Blender Claude MCP Connector

A lightweight, reliable bridge that lets **Claude Code control Blender** via a local HTTP server — no external dependencies, no timeouts.

![Blender + Claude](docs/banner.png)

## Why this exists

Existing Blender MCP solutions use raw TCP sockets, which cause frequent timeouts and are hard to debug. This project replaces the socket layer with plain **HTTP on localhost** — making the connection stable, debuggable with `curl`, and easy to extend.

```
Claude Code
    │  stdio JSON-RPC (MCP protocol)
    ▼
blender_mcp_http.py        ← MCP bridge (pure Python stdlib)
    │  HTTP POST localhost:7234
    ▼
claude_blender_addon.py    ← Blender addon (HTTP server)
    │  bpy.app.timers → main thread
    ▼
Blender Python API (bpy)
```

Everything runs **100% locally** — no cloud, no API keys beyond Claude Code itself.

## Features

- ✅ Execute arbitrary Python code in Blender from Claude
- ✅ Get scene info (objects, materials, camera, render settings)
- ✅ Capture viewport screenshots
- ✅ Trigger renders
- ✅ Auto-starts when addon is enabled
- ✅ UI panel in Blender (Properties → Scene → Claude MCP)
- ✅ Thread-safe via `bpy.app.timers` + `queue.Queue`
- ✅ Zero external Python dependencies (stdlib only)
- ✅ Works with Blender 4.x and 5.x

## Installation

### 1 — Blender Addon

1. Download [`claude_blender_addon.py`](claude_blender_addon.py)
2. In Blender: `Edit > Preferences > Add-ons > Install`
3. Select the file → enable the checkbox ✓
4. The server starts automatically on `localhost:7234`
5. Verify: `Properties > Scene > Claude MCP` shows **● Attivo**

> If the server doesn't auto-start, open the Scripting tab and run:
> ```python
> import bpy
> bpy.ops.claude.start_server()
> ```

### 2 — MCP Bridge

Add this to your `claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

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

Replace `/path/to/blender_mcp_http.py` with the actual path on your system.

### 3 — Restart Claude Code

Restart Claude Code to load the new MCP server. Done.

## Quick Test

Once everything is running, test from any terminal:

```bash
# Ping
curl http://localhost:7234/ping

# Scene info
curl http://localhost:7234/scene_info

# Execute Python in Blender
curl -X POST http://localhost:7234/execute \
  -H "Content-Type: application/json" \
  -d '{"code": "result = [o.name for o in bpy.data.objects]"}'
```

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
  "code": "result = [o.name for o in bpy.data.objects]"
}
```

Assign any JSON-serialisable value to `result` to get data back.

### `/render` body

```json
{
  "filepath": "//my_render.png"
}
```

## MCP Tools (Claude Code)

When connected via the MCP bridge, Claude has access to:

| Tool | Description |
|------|-------------|
| `execute_blender_code` | Run Python in Blender, return `result` |
| `get_scene_info` | Inspect current scene |
| `ping_blender` | Check connection |
| `get_screenshot` | Capture viewport |
| `render_scene` | Render and save |

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

`bpy.app.timers.register()` is thread-safe and designed for exactly this use case.

### Why HTTP over raw sockets?

| | Raw TCP socket | HTTP (this project) |
|-|---------------|---------------------|
| Request framing | Manual | Built-in |
| Timeouts | Manual | Native |
| Debugging | Hard | `curl` |
| Partial reads | Possible | Impossible |
| Reconnection | Manual | Automatic |

## Comparison with other solutions

| Project | Protocol | Port | Deps | Stable |
|---------|----------|------|------|--------|
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) | TCP socket | 9876 | Yes | Sometimes |
| [Blender Lab MCP](https://projects.blender.org/lab/blender_mcp) | stdio+socket | 9876 | Yes | Good |
| **This project** | **HTTP** | **7234** | **None** | **Yes** |

## Requirements

- Blender 4.0 or later (tested on 5.1)
- Python 3.8+ for the bridge (stdlib only)
- Claude Code

## License

MIT — see [LICENSE](LICENSE)

## Contributing

PRs welcome! Ideas:
- [ ] WebSocket support for real-time updates
- [ ] Authentication token for the HTTP server
- [ ] More Blender-specific endpoints (materials, render passes)
- [ ] Blender Extension Marketplace packaging (`blender_manifest.toml`)
- [ ] Auto-reconnect in the bridge
