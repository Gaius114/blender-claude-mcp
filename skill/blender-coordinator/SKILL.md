---
description: >
  Coordinator per la pipeline di modellazione 3D in Blender. Riceve la richiesta
  dell'utente, decide se serve ricerca (blender-research), analizza lo spec_sheet,
  sceglie la tecnica di modellazione per ogni parte, pianifica le dipendenze e
  l'ordine di costruzione, poi orchestra blender-arch. È il "project manager" della
  pipeline: blender-research → coordinator → blender-arch.
  Trigger: qualsiasi richiesta di creazione di oggetti 3D ("voglio creare X").
allowed-tools:
  - Bash
  - Read
  - Write
  - WebSearch
  - mcp__Blender__execute_blender_code
  - mcp__Blender__get_objects_summary
  - mcp__Blender__get_screenshot_of_window_as_image
  - mcp__Blender__render_viewport_to_path
---

# Skill: Blender Coordinator

Sei l'architetto della pipeline di modellazione 3D. Il tuo ruolo è trasformare
una richiesta (vaga o dettagliata) in un **build_plan** eseguibile, coordinando
la ricerca e la modellazione senza sovrapporre le responsabilità.

---

## PIPELINE COMPLETA

```
UTENTE: "voglio creare X"
        │
        ▼
[COORDINATOR — questa skill]
        │
        ├─► STEP 0: valuta la richiesta
        │     Vaga? → chiama blender-research
        │     Dettagliata? → costruisci spec_sheet manuale
        │
        ├─► STEP 1: analizza spec_sheet
        │     Quante parti? Dipendenze? Complessità?
        │
        ├─► STEP 2: scegli tecnica per ogni parte
        │     (vedi tabella TECNICHE DI MODELLAZIONE)
        │
        ├─► STEP 3: pianifica dipendenze e ordine
        │     Chi dipende da chi? Cosa va fatto prima?
        │
        ├─► STEP 4: pianifica materiali e scena
        │     Materiali condivisi? Luci appropriate?
        │
        └─► STEP 5: produci build_plan
              → passa a blender-arch per l'esecuzione
```

---

## STEP 0 — VALUTA LA RICHIESTA

### Criteri per chiamare blender-research:

| Condizione | Azione |
|-----------|--------|
| Richiesta vaga (solo nome oggetto) | → chiama blender-research |
| Mancano dimensioni | → chiama blender-research |
| Mancano colori/materiali | → chiama blender-research |
| Oggetto con parti multiple non descritte | → chiama blender-research |
| Richiesta dettagliata con misure esplicite | → costruisci spec_sheet diretto |
| Oggetto semplice (sfera, cubo, piano) | → vai diretto a blender-arch |

### Livelli di complessità:

```
SEMPLICE  (1 parte, forma primitiva)      → diretto a blender-arch
MEDIO     (2-4 parti, forme standard)     → research + coordinator + arch
COMPLESSO (5+ parti, forme organiche)     → research + coordinator + arch iterativo
```

---

## STEP 1 — ANALISI SPEC_SHEET

Dopo aver ricevuto lo spec_sheet da blender-research (o averlo costruito):

```python
def analizza_spec(spec_sheet):
    """
    Esamina lo spec_sheet e produce una mappa di complessità per parte.
    """
    analysis = {}
    for part_name, part in spec_sheet["parts"].items():
        analysis[part_name] = {
            "shape_family":  classifica_forma(part["shape"]),
            "complexity":    stima_complessita(part),
            "technique":     scegli_tecnica(part),
            "dependencies":  spec_sheet["dependencies"].get(part_name, None),
            "blender_units": converti_blender_units(part),
        }
    return analysis

def classifica_forma(shape_str):
    """Mappa la descrizione testuale a una famiglia geometrica."""
    shape_str = shape_str.lower()
    if any(k in shape_str for k in ["sphere","ball","round","glob"]):
        return "sphere"
    if any(k in shape_str for k in ["cylinder","tube","pipe","rod"]):
        return "cylinder"
    if any(k in shape_str for k in ["cone","taper","truncat"]):
        return "cone"
    if any(k in shape_str for k in ["disc","disk","flat","plate","saucer"]):
        return "disc"
    if any(k in shape_str for k in ["box","cube","rect","block"]):
        return "box"
    if any(k in shape_str for k in ["arc","loop","curve","bend","hook"]):
        return "curve"
    if any(k in shape_str for k in ["organic","irregular","freeform","sculpt"]):
        return "organic"
    if any(k in shape_str for k in ["lathe","revolv","revolution","vase"]):
        return "lathe"
    return "unknown"
```

---

## STEP 2 — TECNICHE DI MODELLAZIONE

Per ogni parte, scegli la tecnica più appropriata:

| Famiglia | Tecnica consigliata | Quando usarla |
|----------|--------------------|----|
| `sphere` | `UV_SPHERE` + sculpt | Frutta, teste, oggetti rotondi |
| `cylinder` | `CYLINDER` + bevel | Tazze, barattoli, colonne |
| `cone` | `CONE` o bmesh rings | Imbuti, coni, beakers |
| `disc` | `CIRCLE` + fill + extrude | Piatti, coperchi, monete |
| `box` | `CUBE` + loop cuts | Mobili, scatole, edifici |
| `curve` | Bezier/NURBS + bevel | Manici, fili, tubi curvi |
| `organic` | UV_SPHERE + sculpt_brush | Frutti, rocce, forme libere |
| `lathe` | bmesh profile rings | Vasi, bottiglie, oggetti di rivoluzione |
| `flat_sheet` | `PLANE` + subdivide | Foglie, tessuti, piani |

### Pattern di codice per ogni tecnica:

```python
# ── UV_SPHERE (frutta, palloni) ──────────────────────────────────
"""
bpy.ops.mesh.primitive_uv_sphere_add(
    radius=r,          # dal spec_sheet: width_cm/2 * 0.01
    segments=64,       # più segmenti = più definizione
    ring_count=48,
    location=(0,0,0)
)
# Poi: origin_set, safe_place, sculpt per dettagli
"""

# ── CYLINDER (tazze, barattoli) ──────────────────────────────────
"""
# Preferire bmesh rings per controllo preciso del taper:
top_r  = spec["diam_top_cm"]  / 2 * 0.01
bot_r  = spec["diam_bot_cm"]  / 2 * 0.01
height = spec["height_cm"] * 0.01
# → crea rings a z=0 e z=height con raggi diversi
# → bridge per pareti, fill per fondo
"""

# ── CURVE LOOP (manici, fili) ────────────────────────────────────
"""
# Genera N punti sul percorso, estrudi sezione circolare:
for i, pt in enumerate(path_points):
    tang = calcola_tangente(path_points, i)
    ring = crea_ring_perpendicolare(pt, tang, radius, segs)
    rings.append(ring)
# → bridge anelli consecutivi
"""

# ── LATHE / REVOLUTION (vasi, bottiglie) ────────────────────────
"""
# Definisci profilo 2D (lista di (r, z) in cm * 0.01):
profile = [(r0,z0), (r1,z1), ...]
# Genera rings a ogni altezza z con raggio r
# → bridge per pareti, fill per fondo
"""

# ── DISC + INSET (piatti, coperchi) ─────────────────────────────
"""
# Rings concentrici con z diversi per creare depressioni/rilievi:
r_outer = ring(bm, OR, z_top)
r_inner = ring(bm, IR, z_top)
r_dep   = ring(bm, IR, z_top - depth)
bridge(bm, r_outer, r_inner)   # piano
bridge(bm, r_inner, r_dep)     # parete depressione
"""
```

---

## STEP 3 — PIANIFICAZIONE DIPENDENZE

```python
def pianifica_ordine(spec_sheet):
    """
    Topological sort delle parti in base alle dipendenze.
    Garantisce che ogni parte sia creata dopo la sua dipendenza.
    """
    deps  = spec_sheet.get("dependencies", {})
    parts = list(spec_sheet["parts"].keys())

    # Kahn's algorithm (topological sort)
    in_degree = {p: 0 for p in parts}
    graph = {p: [] for p in parts}
    for child, parent in deps.items():
        graph[parent].append(child)
        in_degree[child] += 1

    queue  = [p for p in parts if in_degree[p] == 0]
    order  = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order   # lista ordinata: prima le parti indipendenti

# Esempio:
# spec: body (indipendente), handle (dipende da body), saucer (dipende da body)
# → ordine: [body, handle, saucer]  o  [body, saucer, handle]
```

### Regole di posizionamento:

```python
# ── METODO PREFERITO: attach_to / attach_bounds ──────────────────────────
# Precisione < 0.5 μm, funziona con oggetti ruotati, scalati, con parent.
# Disponibile in blender-arch come funzioni già testate.

POSIZIONAMENTO = {
    # Parte indipendente → origin al fondo, appoggiata a z=0
    "center":
        "safe_place(obj, 0, 0, 0, anchor='bottom')",

    # Parte sopra un'altra → usa attach_bounds (allinea bottom di B con top di A)
    "top":
        "attach_bounds(obj_b, 'bottom', obj_a, 'top', gap=0.0)",

    # Parte sotto un'altra → usa attach_bounds inverso
    "bottom":
        "attach_bounds(obj_b, 'top', obj_a, 'bottom', gap=-gap)",

    # Parte laterale → usa attach_to con punti locali espliciti
    "side":
        "attach_to(obj_b, pt_b_local, obj_a, pt_a_local)",

    # Parte che si attacca a un punto preciso (es. manico sulla tazza)
    "attached_to:X":
        "attach_to(obj_b, (0,0,z_local_b), obj_a, (r_local_a, 0, z_local_a))",
}

# Esempi pratici:
#   Cilindro sopra cubo:   attach_bounds(cyl, 'bottom', cube, 'top')
#   Manico su tazza:       attach_to(handle_top, (0,0,-loop_h/2), cup, (top_r, 0, attach_top_z))
#   Oggetto con gap 2mm:   attach_bounds(obj_b, 'bottom', obj_a, 'top', gap=0.002)

# Funzioni world-space (incluse in blender-arch ATTACH POINT SYSTEM):
#   world_bounds(obj)                          → {'min','max','center','size'} in world coords
#   attach_to(obj_b, pt_b, obj_a, pt_a, ...)  → sposta obj_b, ritorna residual (m)
#   attach_bounds(obj_b, face_b, obj_a, face_a, gap) → sposta obj_b per bbox face

# ⚠️ DEPRECATO — NON usare:
#   obj.location.z = parent_zmin - obj_height   (fragile, ignora rotation/parent)
#   stack_on_top(parent, obj)                   (non tiene conto di matrix_world)
# Usa SEMPRE world_bounds() per misurare prima di posizionare
# Mai usare obj.location direttamente senza correzione dell'offset
```

---

## STEP 4 — PIANIFICAZIONE MATERIALI E SCENA

### Raggruppamento materiali:

```python
def raggruppa_materiali(spec_sheet):
    """
    Identifica le parti che condividono lo stesso materiale.
    Evita di creare materiali duplicati.
    """
    mat_groups = {}
    for part_name, part in spec_sheet["parts"].items():
        mat = part["material"]
        # Chiave = tipo + roughness arrotondato + metallic
        key = f"{mat['type']}_{round(mat['roughness'],1)}_{round(mat['metallic'],1)}"
        if key not in mat_groups:
            mat_groups[key] = {
                "parts": [],
                "props": mat,
                "color": part["color_rgb"],
            }
        mat_groups[key]["parts"].append(part_name)
    return mat_groups

# Esempio tazza espresso → 1 solo materiale "Porcelain" per Cup+Handle+Saucer
```

### Template luci per tipo di oggetto:

```python
LIGHT_PRESETS = {
    "small_object": {   # tazze, frutti, oggetti da tavolo
        "key":  {"type":"AREA",  "energy":80,  "size":0.25, "pos":(-0.3,-0.15,0.4)},
        "fill": {"type":"AREA",  "energy":20,  "size":0.5,  "pos":(0.3, 0.1, 0.2)},
        "rim":  {"type":"SPOT",  "energy":45,  "size":0.25, "pos":(0.0, 0.3, 0.3)},
    },
    "furniture": {       # sedie, tavoli
        "key":  {"type":"AREA",  "energy":200, "size":1.0,  "pos":(-1.5,-0.8,2.0)},
        "fill": {"type":"AREA",  "energy":60,  "size":2.0,  "pos":(1.5, 0.5, 1.0)},
        "rim":  {"type":"SPOT",  "energy":150, "size":0.5,  "pos":(0.0, 2.0, 1.5)},
    },
    "architectural": {   # stanze, edifici
        "key":  {"type":"SUN",   "energy":3,               "pos":(5, -5, 8)},
        "fill": {"type":"AREA",  "energy":500, "size":5.0,  "pos":(-3, 2, 4)},
    },
}

def scegli_preset_luci(spec_sheet):
    w = spec_sheet["real_size_cm"]["width"]
    if w < 30:   return "small_object"
    if w < 200:  return "furniture"
    return "architectural"
```

### Template camera:

```python
def calcola_camera(spec_sheet, angle_deg=35):
    """
    Posiziona la camera per inquadrare l'oggetto completo con margine.
    angle_deg: angolo di elevazione dalla orizzontale (35=3/4 view classica)
    """
    w = spec_sheet["real_size_cm"]["width"]  * 0.01   # Blender units
    h = spec_sheet["real_size_cm"]["height"] * 0.01

    # Distanza per inquadrare con focal 85mm
    # FOV 85mm su 36mm sensor: fov_v ≈ 24°
    fov_half = math.radians(12)
    diag = math.sqrt(w**2 + h**2)
    dist = (diag / 2) / math.tan(fov_half) * 1.3   # 30% margine

    import math
    az = math.radians(40)  # azimuth: leggermente di lato
    el = math.radians(angle_deg)
    cam_x = dist * math.cos(el) * math.sin(az)
    cam_y = -dist * math.cos(el) * math.cos(az)
    cam_z = dist * math.sin(el) + h / 2   # punta al centro dell'oggetto

    return {
        "location": (cam_x, cam_y, cam_z),
        "target":   (0, 0, h / 2),
        "lens":     85,
    }
```

---

## STEP 5 — BUILD PLAN OUTPUT

Il build_plan è il documento che blender-arch riceve per eseguire la modellazione.

```python
build_plan = {

    # ── METADATI ───────────────────────────────────────────────────
    "object":      spec_sheet["object"],
    "description": spec_sheet["description"],
    "complexity":  "simple | medium | complex",

    # ── SCALA ──────────────────────────────────────────────────────
    "blender_units": {
        part_name: {
            "key_dimension_1": value_in_blender_units,
            "key_dimension_2": value_in_blender_units,
            # tutti i valori già moltiplicati per 0.01
        }
        for part_name in spec_sheet["parts"]
    },

    # ── FASI DI COSTRUZIONE ────────────────────────────────────────
    "phases": [
        {
            "phase":      1,
            "part":       "nome_parte",
            "technique":  "UV_SPHERE | CYLINDER | LATHE | CURVE_LOOP | DISC | BOX | SCULPT",
            "depends_on": [],              # parti da creare prima
            "position":   {               # come posizionarla
                "method":   "safe_place | stack_on_top | attach",
                "anchor":   "bottom | center | top",
                "target":   [x, y, z],    # in Blender units
            },
            "blender_units": {},           # dimensioni già convertite
            "features":   [],             # features geometriche da aggiungere
            "technique_notes": "...",     # istruzioni specifiche per blender-arch
        },
        # ... una fase per ogni parte
    ],

    # ── MATERIALI ──────────────────────────────────────────────────
    "materials": [
        {
            "name":       "NomeMateriale",
            "applies_to": ["parte1", "parte2"],  # parti che condividono il mat
            "color_linear": [r, g, b],
            "roughness":   0.0,
            "metallic":    0.0,
            "subsurface":  0.0,
            "coat":        0.0,
            "transmission": 0.0,
            "ior":         1.45,
            "notes":       "...",
        }
    ],

    # ── SCENA ──────────────────────────────────────────────────────
    "scene": {
        "camera":      {"location": [x,y,z], "target": [x,y,z], "lens": 85},
        "light_preset": "small_object | furniture | architectural",
        "world_color":  [r, g, b],
        "world_strength": 0.3,
        "table": {
            "enabled": True,
            "color":   [r, g, b],
            "roughness": 0.6,
        },
        "exposure":    0.0,
    },

    # ── NOTE GENERALI ──────────────────────────────────────────────
    "notes": [
        "nota tecnica 1",
        "nota tecnica 2",
    ],
}
```

---

## ESEMPIO COMPLETO — Tazza Espresso

```python
# Input: spec_sheet dalla blender-research
# Output: build_plan per blender-arch

build_plan = {
    "object":      "espresso_cup",
    "description": "Tazzina espresso italiana, porcellana bianca, con piattino",
    "complexity":  "medium",

    "blender_units": {
        "body":   {"top_r":0.031, "bot_r":0.0225, "height":0.058,
                   "wall":0.0045, "base":0.007},
        "handle": {"loop_h":0.034, "depth":0.024, "tube_r":0.004,
                   "attach_top_z":0.048, "attach_bot_z":0.009},
        "saucer": {"outer_r":0.0575, "height":0.016,
                   "dep_r":0.028, "dep_depth":0.004},
    },

    "phases": [
        {
            "phase": 1,
            "part": "body",
            "technique": "LATHE",
            "depends_on": [],
            "position": {"method":"safe_place", "anchor":"bottom", "target":[0,0,0]},
            "features": ["tapered_walls", "thicker_base", "foot_ring", "rounded_rim"],
            "technique_notes":
                "bmesh rings: 48 segmenti, 6 ring (foot_ext, foot_int, wall_bot, "
                "wall_top, inner_bot, inner_top). Raggio varia linearmente da "
                "bot_r a top_r per il taper. Chiudi fondo con fan di triangoli.",
        },
        {
            "phase": 2,
            "part": "handle",
            "technique": "CURVE_LOOP",
            "depends_on": ["body"],
            "position": {"method":"attach", "anchor":"side",
                         "attach_top_z":0.048, "attach_bot_z":0.009},
            "features": ["d_cross_section", "semicircular_path"],
            "technique_notes":
                "Path: semicerchio in piano XZ, 20 punti, da "
                "(top_r,0,attach_top_z) a (top_r,0,attach_bot_z). "
                "Sezione: cerchio r=0.004, 10 segmenti. "
                "Tangente calcolata su 3 punti consecutivi.",
        },
        {
            "phase": 3,
            "part": "saucer",
            "technique": "DISC",
            "depends_on": ["body"],
            "position": {"method":"stack_below", "ref":"body",
                         "gap": -0.016},   # sotto il fondo della tazza
            "features": ["central_depression", "foot_ring"],
            "technique_notes":
                "bmesh rings: outer(OR,z_top), dep_out(DR+0.004,z_top), "
                "dep_in(DR,z_top), dep_bot(DR,z_top-dep_depth). "
                "Bridge per piano e pareti dep. Fan per chiudere fondo.",
        },
    ],

    "materials": [
        {
            "name":        "Porcelain",
            "applies_to":  ["body", "handle", "saucer"],
            "color_linear": [0.955, 0.940, 0.896],
            "roughness":   0.08,
            "metallic":    0.0,
            "subsurface":  0.0,
            "coat":        0.2,
            "coat_roughness": 0.05,
            "transmission": 0.0,
            "ior":         1.52,
            "notes":       "ShaderNodeMix (RGBA) per variazione noise minima (+2%)",
        },
    ],

    "scene": {
        "camera":       {"location":[0.26,-0.32,0.16], "target":[0,0,0.02], "lens":85},
        "light_preset": "small_object",
        "world_color":  [0.03, 0.03, 0.04],
        "world_strength": 0.15,
        "table": {"enabled":True, "color":[0.08,0.05,0.03], "roughness":0.55},
        "exposure": -0.2,
    },

    "notes": [
        "SEMPRE view_layer.update() dopo cambio location prima di leggere matrix_world",
        "ShaderNodeMixRGB deprecato in Blender 5.x → usa ShaderNodeMix data_type=RGBA",
        "origin_set(ORIGIN_GEOMETRY) subito dopo ogni creazione mesh",
        "world_bounds() per verificare posizione reale prima di ogni posizionamento",
        "SHADE SMOOTH BUG: usa ob.data.shade_smooth() NON bpy.ops.object.shade_smooth() — l'operatore non rimuove sharp_face su mesh bmesh → striature su cilindri/coni. Verifica: ob.data.normals_domain deve essere 'POINT'",
        "Dopo shade_smooth: ob.data.set_sharp_from_angle(angle=math.radians(30)) per marcare edge acuti",
        "POSIZIONAMENTO PRECISO: usa attach_to() / attach_bounds() — precisione < 0.5 μm, funziona con oggetti ruotati/scalati/con parent. Definiti in blender-arch SKILL.md sezione ATTACH POINT SYSTEM",
    ],
}
```

---

## REGOLE D'ORO DEL COORDINATOR

1. **Non sovrapporre responsabilità** — research cerca, coordinator pianifica, arch esegue
2. **Topological sort sempre** — mai assumere l'ordine delle parti, calcolarlo
3. **Un materiale condiviso > N materiali identici** — raggruppa prima di creare
4. **Scala coerente** — converti tutto in Blender units (×0.01) nel build_plan, non in arch
5. **Tecnica esplicita** — blender-arch non deve scegliere la tecnica, il coordinator la decide
6. **Position sempre relativa** — mai coordinate assolute hardcoded, sempre relativo a una parte padre o a z=0
7. **Note errori noti** — includi sempre le gotchas (ShaderNodeMixRGB, view_layer.update, ecc.)
8. **Complexity gating** — se complexity=complex, suggerisci iterazioni incrementali (crea, renderizza, verifica, poi continua)
9. **attach_to() per posizionamenti precisi** — quando due parti devono toccarsi (manico su tazza, saucer sotto cup), specifica i punti locali esatti nel build_plan e delega l'esecuzione ad attach_to(). Mai calcolare manualmente delta_z.
10. **world_bounds() prima di ogni attach** — la posizione reale di un oggetto può differire da obj.location a causa di rotation/scale/parent. Misura sempre in world space.
