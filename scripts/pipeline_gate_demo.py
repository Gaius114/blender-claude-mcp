"""
Pipeline a 2 GATE end-to-end — valida l'integrazione plan_validator nel
blender-coordinator (STEP 5b).

Esegue ESATTAMENTE ciò che la skill aggiornata prescrive:
  GATE 1 (piano): esprimi il build_plan come Plan -> plan_validator.validate
                  deve PASSARE  (Python puro, nessun Blender)
  -> solo se PASS:
  GATE 2 (geometria): build via assembly_kernel -> Assembly.validate deve
                  dare components==1, nonmanifold==0

Se entrambi i gate sono verdi, la decomposizione dello stivale e' sana a
tempo di piano E la geometria che ne risulta e' sana: integrazione coerente.
"""

import sys, urllib.request, json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, r"D:\blender-claude\kernel")
import importlib
import plan_validator as pv
importlib.reload(pv)

BLENDER_URL = "http://localhost:7234"


def blender(code, timeout=120):
    data = json.dumps({"code": code, "timeout": timeout}).encode()
    req = urllib.request.Request(f"{BLENDER_URL}/execute", data=data,
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout + 15).read())
    if "error" in r:
        print("ERR:", r["error"][:1500])
        return None
    return r.get("ok")


# ── GATE 1 — piano (la decomposizione che boot_kernel.py poi costruisce) ─────
def boot_plan():
    # root = upper (modelliamo solo la tomaia); ogni pannello ha il PROPRIO
    # arco di feather (bordo libero) -> NON una boundary condivisa
    P = pv.Plan("upper")
    P.part("upper")
    P.connector("s_vq", "seam", "upper")        # vamp|quarter (interfaccia reale)
    P.connector("s_tc", "seam", "upper")        # toecap|vamp  (interfaccia reale)
    P.connector("bf_q", "boundary", "upper")    # feather del quarter
    P.connector("bf_v", "boundary", "upper")    # feather del vamp
    P.connector("bf_t", "boundary", "upper")    # feather del toecap
    P.connector("b_topline", "boundary", "upper")
    P.connector("b_toe", "boundary", "upper")
    P.part("quarter", "upper", "assembly_kernel", ["s_vq", "b_topline", "bf_q"])
    P.part("vamp", "upper", "assembly_kernel", ["s_vq", "s_tc", "bf_v"])
    P.part("toecap", "upper", "assembly_kernel", ["s_tc", "b_toe", "bf_t"])
    P.real_interfaces = {"s_vq", "s_tc"}        # interfacce reali (reference)
    return P


# ── GATE 2 — geometria via assembly_kernel (stesso decomp del piano) ─────────
GATE2 = r"""
import sys, importlib, math
sys.path.insert(0, r"D:\blender-claude\kernel")
import assembly_kernel as ak
importlib.reload(ak)
from mathutils import Vector
ak._clear()

ST = [(0.000,0.034,0.030,0.085),(0.080,0.045,0.020,0.095),
      (0.160,0.052,0.017,0.075),(0.220,0.046,0.020,0.055),
      (0.270,0.020,0.030,0.043)]
NSt=len(ST); Eg=2.4
def lp(a,b,s): return a+(b-a)*s
def last(t,a):
    f=max(0.,min(.999999,t))*(NSt-1); i=int(f); s=f-i
    x0,w0,b0,p0=ST[i]; x1,w1,b1,p1=ST[min(i+1,NSt-1)]
    x=lp(x0,x1,s); hw=lp(w0,w1,s); zb=lp(b0,b1,s); zt=lp(p0,p1,s)
    cz=(zb+zt)*.5; hz=(zt-zb)*.5; ca=math.cos(a); sa=math.sin(a)
    return Vector((x, math.copysign(abs(ca)**(2/Eg),ca)*hw,
                   cz+math.copysign(abs(sa)**(2/Eg),sa)*hz))
GAP=0.42; A0=-math.pi/2+GAP; A1=3*math.pi/2-GAP; NR=28; NT=7
def bnd(j): return A0+(A1-A0)*(j/(NR-1))
T_VQ, T_TC = 0.42, 0.74
A=ak.Assembly("StivaleGate2")
svq=A.seam("s_vq",[last(T_VQ,bnd(j)) for j in range(NR)])
stc=A.seam("s_tc",[last(T_TC,bnd(j)) for j in range(NR)])
def mk(tA,tB):
    def m(r,t): return last(lp(tA,tB,t), bnd(round(r*(NR-1))))
    return m
A.panel_on_master(mk(0.0,T_VQ),NR,NT,edge_t1=svq,material=(0.052,0.030,0.014))
A.panel_on_master(mk(T_VQ,T_TC),NR,NT,edge_t0=svq,edge_t1=stc,
                  material=(0.060,0.034,0.016))
A.panel_on_master(mk(T_TC,1.0),NR,NT,edge_t0=stc,material=(0.045,0.026,0.012))
A.finalize(weld=True)
m=A.validate()
result={"validate":m,"GATE2_PASS":bool(m["components"]==1 and m["nonmanifold"]==0)}
"""


if __name__ == "__main__":
    print("=" * 60)
    print("PIPELINE A 2 GATE — integrazione plan_validator nel coordinator")
    print("=" * 60)

    # GATE 1
    P = boot_plan()
    rep = pv.validate(P)
    g1 = rep["PASS"]
    triggered = {k: v for k, v in rep["rules"].items() if v}
    print(f"  GATE 1 (piano) PASS = {g1}")
    if triggered:
        print("   regole scattate:", json.dumps(triggered, ensure_ascii=False))

    if not g1:
        print("  STOP: piano non valido -> NON si dispaccia (come da STEP 5b)")
        print("Done.")
        sys.exit(0)

    # GATE 2 (solo se GATE 1 passa)
    r = blender(GATE2, timeout=120)
    g2 = bool(r and r.get("GATE2_PASS"))
    print(f"  GATE 2 (geometria) PASS = {g2}  -> {r.get('validate') if r else None}")

    print("-" * 60)
    print(f"  INTEGRAZIONE COERENTE = {bool(g1 and g2)}  "
          f"(piano sano PRIMA, geometria sana DOPO)")
    print("Done.")
