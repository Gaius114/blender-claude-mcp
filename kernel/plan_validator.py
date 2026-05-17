"""
plan_validator — validatore di decomposizione (livello pianificazione)
=======================================================================
Paradigma di decomposizione: un target complesso si scompone in parti
piccole, ognuna con un CONTRATTO d'interfaccia (i connettori che la
delimitano), e a ogni foglia si assegna un METODO dalla libreria validata.

I confini della decomposizione SONO i connettori (cut-line = SeamCurve/
JunctionPoint/boundary). Il piano e' un artefatto VALIDABILE *prima* di
modellare: questo modulo intercetta a tempo di pianificazione le classi di
bug che ci sono costate iterazioni in geometria:
  - connettore non condiviso / duplicato  (= bug "throat != linea-lacci")
  - foglia con metodo incapace di onorare un bordo vincolato esatto
  - connettore "posseduto" da una foglia invece che dal padre coordinatore

Python puro: nessun Blender. `selftest()` = piano-stivale GOOD + 3
controlli negativi, ognuno isola UNA regola.
"""

from dataclasses import dataclass, field

# Metodi che sanno emettere un BORDO VINCOLATO ESATTO (rigenerare una
# curva condivisa). sculpt/geonodes lavorano per displacement/scatter:
# NON rigenerano un boundary esatto -> non possono onorare un seam/junction.
METHOD_EXACT_BOUNDARY = {
    "arch", "procedural", "assembly_kernel", "stitch", "lathe",
}
ALL_METHODS = METHOD_EXACT_BOUNDARY | {"sculpt", "geonodes"}

SEAMLIKE = {"seam", "junction"}   # connettori che richiedono >=2 lati


@dataclass
class Connector:
    id: str
    kind: str          # 'seam' | 'junction' | 'boundary'
    owner: str         # id della parte che lo possiede (deve essere INTERNA)


@dataclass
class Part:
    id: str
    parent: str | None = None
    children: list = field(default_factory=list)   # se interno
    method: str | None = None                      # se foglia
    bound: list = field(default_factory=list)      # connettori sul BORDO
    spans: list = field(default_factory=list)      # interfacce reali INTERNE
                                                   # (se non vuoto su una
                                                   # foglia => va decomposta)

    @property
    def is_leaf(self):
        return not self.children


class Plan:
    def __init__(self, root_id):
        self.root = root_id
        self.parts = {}
        self.connectors = {}
        # interfacce REALI del target (dichiarate da ricerca/reference):
        # il validator non le inventa, verifica la consistenza dato questo set
        self.real_interfaces = set()

    def part(self, pid, parent=None, method=None, bound=None, spans=None):
        p = Part(pid, parent, [], method, list(bound or []), list(spans or []))
        self.parts[pid] = p
        if parent is not None:
            self.parts[parent].children.append(pid)
        return p

    def connector(self, cid, kind, owner):
        c = Connector(cid, kind, owner)
        self.connectors[cid] = c
        return c

    # quali foglie vincolano un dato connettore
    def binders(self, cid):
        return [p.id for p in self.parts.values()
                if p.is_leaf and cid in p.bound]


def validate(plan: Plan):
    R = {"R1_ownership": [], "R2_shared": [], "R3_method": [],
         "R4_referential": [], "R5a_termination": [], "R5b_partition": [],
         "R6_granularity_warn": []}

    # R4 — integrita' referenziale (prima: serve un albero sano)
    if plan.root not in plan.parts:
        R["R4_referential"].append(f"root '{plan.root}' inesistente")
    for p in plan.parts.values():
        if p.parent is not None and p.parent not in plan.parts:
            R["R4_referential"].append(f"{p.id}: parent '{p.parent}' inesistente")
        if p.is_leaf:
            if p.method is None:
                R["R4_referential"].append(f"foglia {p.id}: nessun metodo")
            elif p.method not in ALL_METHODS:
                R["R4_referential"].append(f"{p.id}: metodo ignoto '{p.method}'")
            for cid in p.bound:
                if cid not in plan.connectors:
                    R["R4_referential"].append(
                        f"{p.id}: connettore '{cid}' inesistente")
        else:
            if p.method or p.bound:
                R["R4_referential"].append(
                    f"interno {p.id}: non deve avere method/bound")

    # R1 — ogni connettore posseduto da una parte INTERNA esistente
    for c in plan.connectors.values():
        o = plan.parts.get(c.owner)
        if o is None:
            R["R1_ownership"].append(f"{c.id}: owner '{c.owner}' inesistente")
        elif o.is_leaf:
            R["R1_ownership"].append(
                f"{c.id}: owner '{c.owner}' e' una FOGLIA "
                f"(un connettore va posseduto dal padre coordinatore)")

    # connettori solo "spanned" da una foglia = interfacce PENDING (non
    # ancora tagli): le gestisce R5a, non R2 (non sono cuciture a 1 lato)
    spanned = {cid for p in plan.parts.values() if p.is_leaf
               for cid in p.spans}
    # R2 — sharing: seam/junction richiedono >=2 lati; boundary esattamente 1
    for c in plan.connectors.values():
        b = plan.binders(c.id)
        if c.kind in SEAMLIKE and len(b) < 2 and c.id not in spanned:
            R["R2_shared"].append(
                f"{c.id} ({c.kind}): vincolato da {len(b)} parte/i {b} "
                f"- una cucitura DEVE essere condivisa da >=2 (sorgente non "
                f"sincronizzata = bug throat!=lacci)")
        if c.kind == "boundary" and len(b) != 1:
            R["R2_shared"].append(
                f"{c.id} (boundary): vincolato da {len(b)} parti {b} "
                f"- un bordo libero dichiarato ne vuole esattamente 1")

    # R3 — metodo capace di onorare il contratto
    for p in plan.parts.values():
        if not p.is_leaf:
            continue
        needs_exact = any(plan.connectors[cid].kind in SEAMLIKE
                          for cid in p.bound if cid in plan.connectors)
        if needs_exact and p.method not in METHOD_EXACT_BOUNDARY:
            seams = [cid for cid in p.bound
                     if cid in plan.connectors
                     and plan.connectors[cid].kind in SEAMLIKE]
            R["R3_method"].append(
                f"{p.id}: metodo '{p.method}' NON puo' emettere un bordo "
                f"vincolato esatto, ma deve onorare {seams}")

    # R5a — TERMINAZIONE: una foglia con un'interfaccia REALE al suo interno
    # e' sotto-decomposta (= il "calzino"): va tagliata a quella discontinuita'
    for p in plan.parts.values():
        if not p.is_leaf:
            continue
        for cid in p.spans:
            if cid not in plan.real_interfaces:
                R["R4_referential"].append(
                    f"{p.id}: spans '{cid}' non e' un'interfaccia reale "
                    f"dichiarata")
        real_inside = [cid for cid in p.spans if cid in plan.real_interfaces]
        if real_inside:
            R["R5a_termination"].append(
                f"foglia {p.id}: interfaccia reale {real_inside} CADE DENTRO "
                f"- decomporre alla discontinuita' di ricetta (sotto-decomp.)")

    # R5b — PARTIZIONE: ogni connettore usato come TAGLIO fra fratelli
    # (seam/junction condiviso) DEVE essere un'interfaccia reale dichiarata;
    # altrimenti e' una cucitura inventata (sovra-decomposizione)
    for c in plan.connectors.values():
        if c.kind not in SEAMLIKE:
            continue
        b = plan.binders(c.id)
        if len(b) >= 2 and c.id not in plan.real_interfaces:
            R["R5b_partition"].append(
                f"{c.id} ({c.kind}): taglio fra {b} ma NON e' un'interfaccia "
                f"reale dichiarata - cucitura inventata (sovra-decomp.)")
    # ogni interfaccia reale dev'essere realizzata (esiste come connettore)
    for rid in plan.real_interfaces:
        if rid not in plan.connectors:
            R["R5b_partition"].append(
                f"interfaccia reale '{rid}' dichiarata ma non realizzata "
                f"come connettore nel piano")

    # R6 — granularita' (solo warning, euristiche di contorno)
    for p in plan.parts.values():
        if not p.is_leaf and len(p.children) == 1:
            R["R6_granularity_warn"].append(
                f"{p.id}: nodo interno con 1 solo figlio (annidamento inutile)")
        if p.is_leaf and len(p.bound) > 4:
            R["R6_granularity_warn"].append(
                f"{p.id}: {len(p.bound)} connettori (foglia sovra-vincolata?)")

    hard = ("R1_ownership", "R2_shared", "R3_method", "R4_referential",
            "R5a_termination", "R5b_partition")
    ok = all(not R[k] for k in hard)
    return {"PASS": ok, "rules": R}


# ── SELF-TEST ────────────────────────────────────────────────────────────────
def _good_boot():
    P = Plan("boot")
    P.part("boot")
    P.part("upper", "boot")
    P.part("bottom", "boot")
    # connettori (cut-line) posseduti dal padre coordinatore
    P.connector("s_vq", "seam", "upper")        # vamp|quarter
    P.connector("s_tc", "seam", "upper")        # toecap|vamp
    P.connector("j_throat", "junction", "upper")
    P.connector("b_topline", "boundary", "upper")
    P.connector("b_toe", "boundary", "upper")
    P.connector("s_feather", "seam", "boot")    # upper<->bottom (padre comune)
    P.connector("b_outsole", "boundary", "bottom")
    # foglie upper
    P.part("quarter", "upper", "assembly_kernel", ["s_vq", "b_topline",
                                                   "s_feather"])
    P.part("vamp", "upper", "assembly_kernel", ["s_vq", "s_tc", "j_throat",
                                                "s_feather"])
    P.part("toecap", "upper", "assembly_kernel", ["s_tc", "b_toe"])
    P.part("tongue", "upper", "assembly_kernel", ["j_throat"])
    # foglie bottom
    P.part("midsole", "bottom", "arch", ["s_feather"])
    P.part("outsole", "bottom", "arch", ["b_outsole"])
    # interfacce REALI del bootmaking (da reference): il validator verifica
    # consistenza dato questo set, non lo inventa
    P.real_interfaces = {"s_vq", "s_tc", "j_throat", "s_feather"}
    return P


def _bad_unshared():
    """Bug throat!=lacci a tempo di piano: vamp e quarter NON condividono
    la stessa cucitura, ognuno ha la propria -> R2."""
    P = _good_boot()
    # rimpiazza s_vq condivisa con due seam separate (ognuno 1 lato)
    del P.connectors["s_vq"]
    P.real_interfaces.discard("s_vq")          # isola il sintomo su R2
    P.connector("s_v", "seam", "upper")
    P.connector("s_q", "seam", "upper")
    P.parts["vamp"].bound = ["s_v", "s_tc", "j_throat", "s_feather"]
    P.parts["quarter"].bound = ["s_q", "b_topline", "s_feather"]
    return P


def _bad_method():
    """toecap deve onorare la cucitura esatta s_tc ma usa 'sculpt' -> R3."""
    P = _good_boot()
    P.parts["toecap"].method = "sculpt"
    return P


def _bad_owner():
    """s_vq posseduta da una foglia ('vamp') invece che dal padre -> R1."""
    P = _good_boot()
    P.connectors["s_vq"].owner = "vamp"
    return P


def _bad_underdecomp():
    """SOTTO-decomposizione (= il "calzino"): 'upper' tenuto come UN'unica
    foglia mentre interfacce reali (s_vq/s_tc/j_throat) cadono al suo
    interno -> R5a. (Niente le binda: sono 'spans' pendenti, non tagli.)"""
    P = Plan("boot")
    P.part("boot")
    P.connector("s_vq", "seam", "boot")
    P.connector("s_tc", "seam", "boot")
    P.connector("j_throat", "junction", "boot")
    P.connector("b_topline", "boundary", "boot")
    P.connector("b_toe", "boundary", "boot")
    P.connector("s_feather", "seam", "boot")
    P.connector("b_outsole", "boundary", "bottom")
    P.part("bottom", "boot")
    # 'upper' = UNA foglia che si mangia 3 interfacce reali interne
    P.part("upper", "boot", "assembly_kernel",
           bound=["b_topline", "b_toe", "s_feather"],
           spans=["s_vq", "s_tc", "j_throat"])
    P.part("midsole", "bottom", "arch", ["s_feather"])
    P.part("outsole", "bottom", "arch", ["b_outsole"])
    P.real_interfaces = {"s_vq", "s_tc", "j_throat", "s_feather"}
    return P


def _bad_invented():
    """SOVRA-decomposizione: un taglio 's_fake' fra due pezzi che NON e'
    un'interfaccia reale dichiarata -> R5b (cucitura inventata)."""
    P = _good_boot()
    P.connector("s_fake", "seam", "upper")          # taglio non reale
    P.parts["vamp"].bound.append("s_fake")
    P.parts["toecap"].bound.append("s_fake")        # >=2 lati ma non reale
    return P


def selftest():
    cases = {
        "GOOD_boot":        (_good_boot(),        True,  None),
        "BAD_unshared":     (_bad_unshared(),     False, "R2_shared"),
        "BAD_method":       (_bad_method(),       False, "R3_method"),
        "BAD_owner":        (_bad_owner(),        False, "R1_ownership"),
        "BAD_underdecomp":  (_bad_underdecomp(),  False, "R5a_termination"),
        "BAD_invented":     (_bad_invented(),     False, "R5b_partition"),
    }
    out = {}
    all_ok = True
    for name, (plan, expect_pass, expect_rule) in cases.items():
        rep = validate(plan)
        passed = rep["PASS"]
        if expect_pass:
            isolates = passed
        else:
            triggered = [k for k, v in rep["rules"].items()
                         if v and k != "R6_granularity_warn"]
            isolates = (not passed) and triggered == [expect_rule]
        all_ok &= isolates
        out[name] = {
            "PASS": passed,
            "expected_pass": expect_pass,
            "expected_rule": expect_rule,
            "triggered": {k: v for k, v in rep["rules"].items() if v},
            "isolates_correctly": isolates,
        }
    out["SELFTEST_OK"] = bool(all_ok)
    return out


if __name__ == "__main__":
    import json
    r = selftest()
    for name, d in r.items():
        if name == "SELFTEST_OK":
            continue
        tag = "OK " if d["isolates_correctly"] else "XX "
        print(f"{tag}{name}: PASS={d['PASS']} "
              f"(atteso pass={d['expected_pass']}, "
              f"regola attesa={d['expected_rule']})")
        for rule, msgs in d["triggered"].items():
            for m in msgs:
                print(f"      [{rule}] {m}")
    print("=" * 60)
    print("SELFTEST_OK:", r["SELFTEST_OK"])
