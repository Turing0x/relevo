#!/usr/bin/env python3
# Resume ~/.claude/orchestrator/log.jsonl por agente. Uso: stats.py [días] (por defecto 30).
# out~ es estimación (caracteres generados / 4, sin thinking); ctx~ = entrada + caché leída + caché escrita.
import json, os, re, sys
from collections import defaultdict
from datetime import datetime, timedelta

LOG = os.environ.get("ORCH_LOG") or os.path.expanduser("~/.claude/orchestrator/log.jsonl")

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
    print(f"{'agente':<14}{'n':>4}{'modelo':>24}{'turnos~':>8}{'tope':>6}{'out~':>8}{'ctx~':>9}{'seg~':>6}  estados")
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
              f"{mean(rs, 'out_est'):>8.0f}{ctx:>9.0f}{mean(rs, 'dur_s'):>6.0f}  "
              + " ".join(f"{k}:{v}" for k, v in sorted(st.items(), key=lambda kv: -kv[1])))

main()
