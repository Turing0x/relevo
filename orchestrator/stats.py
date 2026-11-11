#!/usr/bin/env python3
# Resume ~/.claude/orchestrator/log.jsonl por agente. Uso: stats.py [días] (por defecto 30).
# out~ es estimación (caracteres generados / 4, sin thinking); ctx~ = entrada + caché leída + caché escrita.
# La duración es la mediana (seg.med) porque hay outliers.
# $~ = coste estimado a precio de lista; la telemetría no distingue el TTL de la caché, se asume el de 1 h.
import json, os, re, sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

LOG = os.environ.get("ORCH_LOG") or os.path.expanduser("~/.claude/orchestrator/log.jsonl")

# $/MTok de lista, tabla del 2026-11-03. Estimación: revisar contra la página de precios antes de fiarse.
PRICES = {
    "claude-opus-5-5": {"in": 4.00, "cache_read": 0.20, "out": 20.00},
    "claude-sonnet-5-5": {"in": 2.00, "cache_read": 0.10, "out": 10.00},
    "claude-haiku-5-5": {"in": 0.10, "cache_read": 0.01, "out": 0.50},  # VERIFICAR cache_read (0,1x supuesto); in/out valen hasta 100K de prompt
}
CACHE_WRITE_MULT = 2.0  # Claude Code en suscripción escribe la caché con TTL 1 h

def cost(r):
    p = PRICES.get(r.get("model"))
    if not p:
        return None
    n = lambda k: r[k] if isinstance(r.get(k), (int, float)) else 0
    return (n("in") * p["in"] + n("cache_write") * p["in"] * CACHE_WRITE_MULT
            + n("cache_read") * p["cache_read"] + n("out_est") * p["out"]) / 1e6

def total_cost(rs):
    return sum(c for c in map(cost, rs) if c is not None)

def max_turns(agent, cwd):
    # El agente de proyecto pisa al global: buscar primero en <cwd>/.claude/agents.
    for d in ([os.path.join(cwd, ".claude/agents")] if cwd else []) + [os.path.expanduser("~/.claude/agents")]:
        try:
            m = re.search(r"^maxTurns:\s*(\d+)", open(f"{d}/{agent}.md").read(), re.M)
            return int(m.group(1)) if m else None
        except OSError:
            continue
    return None

def mean(rs, k):
    v = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
    return sum(v) / len(v) if v else 0

def med(rs, k):
    v = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
    return median(v) if v else 0

def main():
    try:
        days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
        since = datetime.now() - timedelta(days=days)
    except (ValueError, OverflowError):
        days, since = 30, datetime.now() - timedelta(days=30)
    rows, last = defaultdict(list), {}
    try:
        for line in open(LOG, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
                if isinstance(r.get("agent"), str) and datetime.fromisoformat(r["ts"]) >= since:
                    # Un subagente reanudado vuelve a disparar SubagentStop: quedarse con su último registro.
                    last[r.get("agent_id") or id(r)] = r
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    except FileNotFoundError:
        print("Sin datos: log.jsonl no existe todavía.")
        return
    for r in last.values():
        rows[r["agent"]].append(r)
    if not rows:
        print(f"Sin llamadas en {days} días.")
        return
    print(f"Últimos {days} días — {sum(map(len, rows.values()))} llamadas")
    print(f"{'agente':<14}{'n':>4}{'modelo':>24}{'turnos~':>8}{'tope':>6}{'out~':>8}{'ctx~':>9}{'seg.med':>8}{'$~':>8}  estados")
    for agent, rs in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        hit = 0
        for r in rs:
            mt = max_turns(agent, r.get("cwd"))
            hit += bool(mt and isinstance(r.get("turns"), int) and r["turns"] >= mt)
        models = sorted({(r.get("model") or "?").replace("claude-", "") for r in rs})
        st = defaultdict(int)
        for r in rs:
            st[r.get("status", "?")] += 1
        ctx = mean(rs, "in") + mean(rs, "cache_read") + mean(rs, "cache_write")
        print(f"{agent:<14}{len(rs):>4}{','.join(models)[-24:]:>24}{mean(rs, 'turns'):>8.1f}{hit:>6}"
              f"{mean(rs, 'out_est'):>8.0f}{ctx:>9.0f}{med(rs, 'dur_s'):>8.0f}{total_cost(rs):>8.2f}  "
              + " ".join(f"{k}:{v}" for k, v in sorted(st.items(), key=lambda kv: -kv[1])))
    allrs = [r for rs in rows.values() for r in rs]
    unpriced = sum(cost(r) is None for r in allrs)
    print(f"Total estimado: ${total_cost(allrs):.2f} (precio de lista; out~ sin thinking → infraestima)"
          + (f"; {unpriced} registros sin precio" if unpriced else ""))
    vrs = rows.get("verificador", [])
    if any(isinstance(r.get("nivel"), str) for r in vrs):
        print("\nPor nivel (verificador, por modelo; el nivel 0 no lanza worker y solo consta en §7)")
        lv = defaultdict(list)
        for r in vrs:
            lv[(r["nivel"] if isinstance(r.get("nivel"), str) else "?",
                (r.get("model") or "?").replace("claude-", ""))].append(r)
        for (nivel, model), rs in sorted(lv.items()):
            mot = defaultdict(int)
            for r in rs:
                if isinstance(r.get("motivo"), str):
                    mot[r["motivo"]] += 1
            rech = sum(r.get("status") == "RECHAZADO" for r in rs)
            print(f"  {nivel:<8}{model:<14}n={len(rs)}  seg.med={med(rs, 'dur_s'):.0f}  RECHAZADO:{rech} ({100 * rech / len(rs):.0f}%)  "
                  f"escalado:{sum(r.get('motivo') == 'escalado' for r in rs)}  $~{total_cost(rs):.2f}  "
                  + " ".join(f"{k}:{v}" for k, v in sorted(mot.items(), key=lambda kv: -kv[1])))

main()
