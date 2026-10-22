# 0006 — Telemetría por hook SubagentStop

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
No había forma de saber si el router acertaba. El maintainer eligió la telemetría vía hook.

## Decisión
`~/.claude/hooks/orch-telemetry` (SubagentStop, `async: true`, `~/.claude/settings.json:113-119`) añade una línea por worker a `~/.claude/orchestrator/log.jsonl`. Solo guarda métricas y la palabra de estado, no contenido. `/orch-stats` la resume (`~/.claude/orchestrator/stats.py`).

## Alternativas
- Registrar desde la política (que el router escriba el log). `[VERIFICAR: no hay registro de que se evaluara]`.

## Consecuencias
- Coste cero de contexto: el hook no imprime nada.
- `out_est` es una estimación (caracteres / 4, sin thinking), porque `usage.output_tokens` del transcript es un snapshot del inicio del streaming (`~/.claude/hooks/orch-telemetry:15-16`).
- El router no consulta la telemetría al enrutar; sirve para ajustar umbrales a mano.
