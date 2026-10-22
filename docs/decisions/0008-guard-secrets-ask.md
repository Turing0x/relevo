# 0008 — guard-secrets pide confirmación, no bloquea

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
`permissions.ask` solo cubría `Read(**/.env*)`; `cat`, `grep` y `rg` vía Bash y la herramienta Grep podían leer secretos (`~/.claude/hooks/guard-secrets:2-4`).

## Decisión
Hook PreToolUse sobre Bash, Grep y Read que devuelve `permissionDecision: "ask"` cuando la llamada nombra `.env`, claves privadas o credenciales (`~/.claude/hooks/guard-secrets`, `~/.claude/settings.json:102-111`).

## Alternativas
- `deny`. Descartada: hay usos legítimos con aprobación humana. Los falsos positivos se asumen como `ask` (`guard-secrets:7`).
- Quitar `Bash` a `Explore`. Descartada: solo cubría a ese worker.

## Consecuencias
- Defensa en profundidad, no sandbox. No detecta un grep recursivo sobre un directorio, la carga implícita (dotenv, printenv), la ofuscación ni la herramienta Glob (`guard-secrets:5-6`).
- Ante una excepción interna, el hook sale con 0 y no pide nada (fail-open, `guard-secrets:73-74`).
