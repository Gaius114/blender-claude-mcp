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
- ✅ 11 modular Claude Code skills covering the full modeling pipeline

---

## Contents

| Path | Description |
|------|-------------|
| `claude_blender_addon.py` | Blender addon v3.0 — HTTP server on port 7234 |
| `blender_mcp_http.py` | MCP bridge: translates MCP JSON-RPC → HTTP to port 7234 |
| `skill/` | 11 Claude Code skills — full modeling pipeline |
| `kernel/` | Panel/seam composition kernel + plan & interface validators (pure Python, self-validating) |
| `scripts/` | Example scripts: donut, espresso cup, wine bottle, fruit basket, bedside lamp |
| `renders/` | Reference renders from each session |

---

## Installation

### 1 — Blender Addon

1. Copy `claude_blender_addon.py` to your Blender addons folder, or:
2. In Blender: `Edit > Preferences > Add-ons > Install` → select the file → enable ✓
3. The server starts automatically on `localhost:7234`
4. Verify: `Properties > Scene > Claude MCP` shows **● Attivo**

> If the server doesn't auto-start, open the Scripting tab and run:
> ```python
> import bpy
> bpy.ops.claude.start_server()
> ```

### 2 — Claude Code Skills

Copy the skill folders to your Claude skills directory:

**macOS / Linux:**
```bash
cp -r skill/blender-* ~/.claude/skills/
```

**Windows:**
```powershell
Copy-Item -Recurse skill\blender-* C:\Users\<you>\.claude\skills\
```

Then invoke in Claude Code with:
```
/blender-coordinator build a bedside lamp
/blender-arch model an espresso cup with saucer
/blender-lighting setup rembrandt lighting for a product shot
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

## Skill Stack (11 skills)

The pipeline is split into focused, composable skills. The coordinator routes each task to the right specialist.

```
User request
    │
    ▼
blender-coordinator  ← entry point, builds the plan, routes to skills
    ├── blender-research    ← spec_sheet from vague requests
    ├── blender-arch        ← rigid objects, architecture, products
    ├── blender-procedural  ← organic tubes, loft, DNA, vascular trees
    ├── blender-sculpt      ← freeform shapes, terrain, fruit
    ├── blender-rig         ← armatures, FK/IK, weight paint, shape keys
    ├── blender-geonodes    ← scatter, curve-to-mesh, noise displacement
    ├── blender-texture     ← UV, PBR materials, baking, SSS
    ├── blender-space       ← precise positioning, attach point system
    ├── blender-lighting    ← 3-point + named cinematic rigs, camera, world
    └── blender-physics     ← rigid body, cloth, particles
```

### Skill details

| Skill | Techniques | Typical use |
|-------|-----------|-------------|
| `blender-coordinator` | build_plan, routing, dependency sort, socket assembly | Any complex object |
| `blender-research` | spec_sheet: dimensions, colors, parts, materials | Vague requests ("make a lamp") |
| `blender-arch` | CUBE/CYL/LATHE + bevel/boolean, attach_to system | Furniture, cups, architecture |
| `blender-procedural` | Parallel Transport, build_shell/vessel, DNA, vascular | Tubes, bones, organic loft |
| `blender-sculpt` | KDTree brush, 5 falloff kernels, noise3d, remesh | Fruit, rocks, terrain |
| `blender-rig` | Armature, bone roll=0, IK, weight paint, shape keys | Characters, hands, eyelids |
| `blender-geonodes` | Scatter, curve-to-mesh, noise deform via GN Python | Sprinkles, grass, cables |
| `blender-texture` | UV unwrap, mat_pbr/noise/glass/metal/fabric, bake AO | All materials and textures |
| `blender-space` | attach_to(), attach_bounds(), safe_place(), world_bounds() | Assembly phase |
| `blender-lighting` | 3-point, Loop/Rembrandt/Butterfly/Split/High-Key/Low-Key, HDRI | Product shots, food, portraits |
| `blender-physics` | Rigid body, cloth, fluid, particles | Simulations |

---

## Panel/Seam Kernel — Two-Gate Pipeline

`kernel/` formalizes how **panelized, seamed objects** (footwear, bags,
upholstery, shells) are built — the failure mode of one-shot loft/boolean
modeling (the "sock blob") is eliminated *by construction*, not by discipline.

**Model (validated with objective metrics):** local authoring + **rigid
SE(3) placement** + cuts as **shared connectors** (`SeamCurve` 1-D,
`JunctionPoint` 0-D) + an **anti-drift frame field** for curvature. A
complex shape *emerges* from composing simple curved pieces, never one shot.

| Module | Role |
|--------|------|
| `kernel/derive_interfaces.py` | Typed adjacency graph → real interfaces via an S1×S2 concordance rule (junctions derived from 3-cliques) |
| `kernel/plan_validator.py` | Decomposition gate: 6 hard rules catch bad plans **before any geometry** |
| `kernel/assembly_kernel.py` | Geometry: `Frame`, `parallel_transport`, `Assembly` (`panel_on_master`, `swept_piece`, `validate`) |

**Two-gate pipeline** (enforced by `blender-coordinator` STEP 5b +
`blender-arch`): `derive` → **plan gate** (`plan_validator.validate`,
sound decomposition) → build → **geometry gate** (`Assembly.validate`:
1 component / 0 non-manifold). Each module ships a `selftest()` — the
proof travels with the code.

---

## Named Lighting Techniques (blender-lighting)

| Technique | Ratio | Best for |
|-----------|-------|----------|
| Loop | 2:1 | Product standard, lifestyle |
| Rembrandt | 3:1–4:1 | Premium product, character |
| Butterfly | 2:1–2.5:1 | Beauty, jewelry, cosmetics |
| Split | 8:1+ | Dark product, thriller |
| High Key | 1:1 | Advertising, happy lifestyle |
| Low Key | 8:1+ | Spirits, horror, noir |
| Food Side | 2:1 | Editorial food, texture |
| Food Window | 2:1 | Lifestyle food, natural light |

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
render_and_read("preview.png")   # → Read tool → visual analysis
blender(fix_code)                # → iterate until satisfied
```

---

## Blender 5.x Gotchas

Critical fixes for Blender 4.x / 5.x — all skills are aware of these:

| Issue | Wrong | Correct |
|-------|-------|---------|
| Smooth shading on bmesh | `bpy.ops.object.shade_smooth()` | `obj.data.shade_smooth()` |
| ShaderNodeMix color blend | `inputs[1]`, `inputs[2]`, `outputs[0]` | `data_type='RGBA'`, `inputs[6]`, `inputs[7]`, `outputs[2]` |
| EEVEE engine name | hardcode `BLENDER_EEVEE_NEXT` (raises on 5.1 → only `BLENDER_EEVEE` exists) | `BLENDER_EEVEE` on 5.1; `try BLENDER_EEVEE_NEXT except BLENDER_EEVEE` for 4.2–4.x |
| Cycles denoiser | `OPTIX` (crashes on some setups) | `OPENIMAGEDENOISE` as safe fallback |
| AgX color (Blender 5.x) | `Filmic` | `AgX` + look `AgX - Punchy` |
| matrix_world stale | read directly | `bpy.context.view_layer.update()` first |

---

## Example Renders

| Object | Technique | Script |
|--------|-----------|--------|
| Donut + icing + sprinkles | GeoNodes scatter | `scripts/donut.py` |
| Espresso cup + saucer | LATHE + attach_to | `scripts/espresso_v2.py` |
| Wine bottle | Hybrid loft | `scripts/bottle_hybrid.py` |
| Fruit basket | Sculpt + GeoNodes | `scripts/basket_final.py` |
| Bedside lamp | LATHE + Rembrandt lighting | `renders/bedside_lamp_FINAL.png` |

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

- Blender 4.0+ (tested on 5.1.1)
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
