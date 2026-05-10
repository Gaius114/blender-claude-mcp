# blender-claude

> Blender 3D modeling via Claude AI — HTTP connector addon + Claude Code skill

A pipeline that lets **Claude Code** control Blender programmatically through a local HTTP server running inside Blender as an addon. Claude executes Python (`bpy`) code, renders previews, analyzes them visually, and iterates — a full **visual loop** for 3D modeling.

---

## Contents

| Path | Description |
|------|-------------|
| `addon/claude_blender_addon.py` | Blender addon v3.0 — HTTP server on port 7234 |
| `skill/SKILL.md` | Claude Code skill with modeling helpers, materials, camera presets |
| `scripts/` | Example scripts: donut, wine bottle, house, fixes |

---

## How it works

```
Claude Code  ──POST /execute──▶  Blender Addon (port 7234)
                                        │
                                   runs bpy code
                                        │
             ◀──── base64 PNG ──  EEVEE render
                                        │
           Read PNG → analyze → iterate
```

1. Install `addon/claude_blender_addon.py` in Blender  
   *(Edit → Preferences → Add-ons → Install)*
2. Enable it and press **Start Server** in the Scene properties panel
3. Claude Code uses the `blender-arch` skill to build 3D objects

---

## Addon features (v3.0)

- Thread-safe Python execution via main thread queue
- EEVEE render → base64 PNG response
- Full `bpy` + `bmesh` + Geometry Nodes access
- Timeout handling, error reporting
- Compatible with Blender 4.x and 5.x

---

## Skill capabilities

The `skill/SKILL.md` covers:

- **Modeling**: box, cylinder, sphere, bmesh extrude, pipe/curve, lathe (revolution)
- **Modifiers**: Bevel, SubSurf, Solidify, Array, Mirror, Boolean
- **Architecture**: walls with openings, window frames, railings, staircases, hip roofs
- **Materials** (Blender 5.x accurate):
  - `mat_pbr`, `mat_noise`, `mat_glass`, `mat_metal` (with Coat/clearcoat)
  - `mat_subsurface` (SSS — skin, wax, marble)
  - `mat_fabric` (Sheen layer — velvet, linen)
  - `mat_wood`, `mat_blueprint`
- **Camera**: 8 presets + DOF
- **Lighting**: 3-point, architectural sun+fill

---

## Example renders

Built with this pipeline:

- Blenderguru-style donut with procedural icing + GeoNodes sprinkles
- Wine bottle (hybrid workflow: bmesh profile + `bpy.ops.mesh.spin`)
- Modern house with Boolean windows, garage, landscape

---

## Requirements

- Blender 4.0+ (tested on 5.1)
- Claude Code with `blender-arch` skill installed at `~/.claude/skills/blender-arch/`

---

*Built with [Claude Code](https://claude.ai/claude-code)*
