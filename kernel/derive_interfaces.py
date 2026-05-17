"""
derive_interfaces — derivazione semi-automatica delle interfacce reali
======================================================================
Stadio PRIMA di plan_validator. Trasforma il grafo di adiacenza tipizzato
(che blender-research dovrebbe emettere) nel set `real_interfaces`, via
due proiezioni dello STESSO artefatto:
  S1 = tipo dell'arco di giunzione
  S2 = discontinuita' di attributo fra i nodi (materiale/metodo/curvatura)

Un connettore = una discontinuita' nella RICETTA. La regola di concordanza
S1xS2 decide: AUTO dove i segnali concordano (o sono benigni); FLAG-umano
solo sulle 2 celle contraddittorie (la minoranza). I JunctionPoint NON si
dichiarano: si derivano dai 3-clique del sottografo delle interfacce.

Pipeline: derive_real_interfaces(G) -> (real_interfaces, review, ...) ->
plan_validator verifica la decomposizione CONTRO questo set derivato.

Python puro (no Blender). `selftest()` = grafo-stivale GOOD + 2 controlli
negativi; output composto con plan_validator.

Refinement emersi VALIDANDO (come il gate che colse il draft del feather):
 - per archi FIXTURE il materiale e' atteso diverso (metallo su pelle):
   s2 NON guarda gli attributi, guarda solo un flag esplicito
   `host_discontinuity` (un fixture per definizione sta su host continuo).
 - (INTERFACE, NONE) = cucitura stesso-materiale: BENIGNO, auto-accetta,
   non flaggare (anti-over-flagging: sennò il "semi" collassa in manuale).
"""

import sys, os, itertools, importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_validator as pv
importlib.reload(pv)

BOUNDARY = {"stitched", "lasted", "welted", "cemented"}
CONTINUOUS = {"continuous"}
FIXTURE = {"hardware-attached"}
ATTRS = ("material", "method", "curvature")


class ResearchGraph:
    def __init__(self):
        self.nodes = {}   # id -> {material, method, curvature}
        self.edges = []   # {a, b, join, host_discontinuity?}

    def node(self, nid, material, method, curvature):
        self.nodes[nid] = {"material": material, "method": method,
                           "curvature": curvature}
        return self

    def edge(self, a, b, join, host_discontinuity=False):
        self.edges.append({"a": a, "b": b, "join": join,
                           "host_discontinuity": host_discontinuity})
        return self


def _s1(join):
    if join in BOUNDARY:
        return "INTERFACE"
    if join in FIXTURE:
        return "FIXTURE"
    if join in CONTINUOUS:
        return "NONE"
    return "UNKNOWN"


def _s2(g, e, s1):
    if s1 == "FIXTURE":
        # un fixture sta su host continuo: materiale atteso diverso ->
        # discontinuita' SOLO se la reference lo dichiara esplicitamente
        return "INTERFACE" if e.get("host_discontinuity") else "NONE"
    na, nb = g.nodes[e["a"]], g.nodes[e["b"]]
    return "INTERFACE" if any(na[k] != nb[k] for k in ATTRS) else "NONE"


# tabella di concordanza S1 x S2
def _decide(s1, s2):
    if s1 == "INTERFACE" and s2 == "INTERFACE":
        return "auto_interface", "concordi"
    if s1 == "INTERFACE" and s2 == "NONE":
        return "auto_interface", "cucitura stesso-materiale (benigno)"
    if s1 == "NONE" and s2 == "NONE":
        return "auto_reject", "pezzo continuo, nessun cambio ricetta"
    if s1 == "FIXTURE" and s2 == "NONE":
        return "auto_fixture", "hardware su host continuo"
    if s1 == "NONE" and s2 == "INTERFACE":
        return "flag", "CONTRADDIZIONE: continuo ma ricetta cambia"
    if s1 == "FIXTURE" and s2 == "INTERFACE":
        return "flag", "fixture ma host discontinuo -> probabile mis-typing"
    return "flag", f"caso ignoto (s1={s1})"


def _eid(a, b):
    return "s_" + "_".join(sorted((a, b)))


def derive_real_interfaces(g: ResearchGraph):
    decisions = {}
    seam_edges = []      # (a,b) auto-interface
    fixtures = []
    review = []
    for e in g.edges:
        s1 = _s1(e["join"])
        s2 = _s2(g, e, s1)
        verdict, why = _decide(s1, s2)
        key = f"{e['a']}~{e['b']}"
        decisions[key] = {"join": e["join"], "s1": s1, "s2": s2,
                          "verdict": verdict, "why": why}
        if verdict == "auto_interface":
            seam_edges.append((e["a"], e["b"]))
        elif verdict == "auto_fixture":
            fixtures.append(key)
        elif verdict == "flag":
            review.append({"edge": key, "why": why})

    # JunctionPoint = 3-clique nel sottografo delle interfacce (derivato,
    # non dichiarato): 3 parti mutuamente cucite -> convergono in un punto
    adj = {}
    for a, b in seam_edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    junctions = []
    for tri in itertools.combinations(sorted(adj), 3):
        x, y, z = tri
        if y in adj[x] and z in adj[x] and z in adj[y]:
            junctions.append({"id": "j_" + "_".join(tri), "parts": list(tri)})

    seams = [{"id": _eid(a, b), "a": a, "b": b} for a, b in seam_edges]
    real_interfaces = {s["id"] for s in seams} | {j["id"] for j in junctions}
    return {"real_interfaces": real_interfaces, "seams": seams,
            "junctions": junctions, "fixtures": fixtures,
            "review": review, "decisions": decisions}


def to_plan(g: ResearchGraph, d, root="asm"):
    """Compone la derivazione in un pv.Plan (root interno possiede i
    connettori; foglie = nodi-parte; metodo da method-domain)."""
    METHOD_MAP = {"paneled": "assembly_kernel", "organic": "sculpt",
                  "primitive": "arch", "tubular": "procedural",
                  "fixture": "arch"}
    P = pv.Plan(root)
    P.part(root)
    part_ids = [nid for nid in g.nodes
                if nid not in {f.split("~")[0] for f in d["fixtures"]}
                and g.nodes[nid]["method"] != "fixture"]
    # connettori posseduti dal root (parte interna coordinatrice)
    for s in d["seams"]:
        P.connector(s["id"], "seam", root)
    for j in d["junctions"]:
        P.connector(j["id"], "junction", root)
    # bordi liberi per ogni foglia (ogni pannello ha il proprio)
    incident = {pid: [] for pid in part_ids}
    for s in d["seams"]:
        if s["a"] in incident:
            incident[s["a"]].append(s["id"])
        if s["b"] in incident:
            incident[s["b"]].append(s["id"])
    for j in d["junctions"]:
        for pid in j["parts"]:
            if pid in incident:
                incident[pid].append(j["id"])
    for pid in part_ids:
        bid = f"b_{pid}"
        P.connector(bid, "boundary", root)
        method = METHOD_MAP.get(g.nodes[pid]["method"], "arch")
        P.part(pid, root, method, incident[pid] + [bid])
    P.real_interfaces = set(d["real_interfaces"])
    return P


# ── SELF-TEST ────────────────────────────────────────────────────────────────
def _good_graph():
    g = ResearchGraph()
    for p in ("quarter", "vamp", "toecap", "tongue"):
        g.node(p, "leather", "paneled", "single")
    g.node("eyelets", "metal", "fixture", "na")
    g.edge("quarter", "vamp", "stitched")
    g.edge("vamp", "toecap", "stitched")
    g.edge("vamp", "tongue", "stitched")
    g.edge("quarter", "tongue", "stitched")     # -> clique throat (q,v,t)
    g.edge("eyelets", "vamp", "hardware-attached")   # fixture, host continuo
    return g


def _nc_contradiction():
    """(continuous, INTERFACE): un arco 'continuo' fra materiali diversi."""
    g = _good_graph()
    g.node("rubberflap", "rubber", "paneled", "single")
    g.edge("vamp", "rubberflap", "continuous")  # continuo ma materiale !=
    return g


def _nc_fixture_mistyped():
    """(FIXTURE, host_discontinuity): hardware ma host dichiarato discontinuo."""
    g = _good_graph()
    g.edges[-1]["host_discontinuity"] = True     # l'arco eyelets~vamp
    return g


def selftest():
    out = {}

    # GOOD: review vuota; junction throat derivata; plan_validator PASS
    g = _good_graph()
    d = derive_real_interfaces(g)
    good_review_empty = (d["review"] == [])
    has_throat = any(set(j["parts"]) == {"quarter", "vamp", "tongue"}
                     for j in d["junctions"])
    P = to_plan(g, d)
    rep = pv.validate(P)
    good_ok = good_review_empty and has_throat and rep["PASS"]
    out["GOOD"] = {"review": d["review"],
                   "junctions": [j["id"] for j in d["junctions"]],
                   "fixtures": d["fixtures"],
                   "real_interfaces": sorted(d["real_interfaces"]),
                   "plan_validator_PASS": rep["PASS"],
                   "rules_triggered": {k: v for k, v in rep["rules"].items()
                                       if v},
                   "OK": good_ok}

    # NC1: la contraddizione finisce in review (e solo quella)
    d1 = derive_real_interfaces(_nc_contradiction())
    nc1_ok = (len(d1["review"]) == 1
              and "vamp~rubberflap" in d1["review"][0]["edge"]
              and "CONTRADDIZIONE" in d1["review"][0]["why"])
    out["NC1_contradiction"] = {"review": d1["review"], "OK": nc1_ok}

    # NC2: il fixture mis-typed finisce in review (e solo quello)
    d2 = derive_real_interfaces(_nc_fixture_mistyped())
    nc2_ok = (len(d2["review"]) == 1
              and "eyelets~vamp" in d2["review"][0]["edge"]
              and "mis-typing" in d2["review"][0]["why"])
    out["NC2_fixture_mistyped"] = {"review": d2["review"], "OK": nc2_ok}

    out["SELFTEST_OK"] = bool(good_ok and nc1_ok and nc2_ok)
    return out


if __name__ == "__main__":
    import json
    r = selftest()
    for k in ("GOOD", "NC1_contradiction", "NC2_fixture_mistyped"):
        d = r[k]
        tag = "OK " if d["OK"] else "XX "
        print(f"{tag}{k}: OK={d['OK']}")
        print("   " + json.dumps({x: y for x, y in d.items() if x != "OK"},
                                  ensure_ascii=False))
    print("=" * 62)
    print("SELFTEST_OK:", r["SELFTEST_OK"])
