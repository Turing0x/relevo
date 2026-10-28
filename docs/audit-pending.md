# Auditoría pendiente: comprobaciones en ejecución

Este archivo lista lo que no se puede determinar leyendo los archivos del orquestador y debe comprobarse ejecutando Claude Code en una sesión nueva. Cada fila corresponde a un `[VERIFICAR]` de otros documentos. Las rutas son absolutas desde `~/.claude/`.

Estado: pendiente. Decisión del maintainer (2026-10-22): se hará en una sesión nueva.

| # | Qué comprobar | Cómo | Afecta a |
|---|---|---|---|
| 1 | Que `~/.claude/agents/Explore.md` sustituye al `Explore` integrado de Claude Code | En sesión nueva, provocar una búsqueda amplia y mirar en `/tasks` o en `log.jsonl` que `model` sea `claude-haiku-5-5` | [agents/Explore.md](agents/Explore.md) |
| 2 | Qué devuelve un worker que alcanza `maxTurns` (reporte parcial, error, nada) | Lanzar `clasificador` (maxTurns 3) con una petición que le obligue a leer mucho | [routing.md](routing.md), fichas de agente, [failure-modes.md](failure-modes.md) |
| 3 | Que `effort` del frontmatter se respeta en haiku | Ver el campo `effort` en `log.jsonl` tras una llamada a `rapido` | [decisions/0002-modelo-por-rol.md](decisions/0002-modelo-por-rol.md) |
| 4 | Que `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` impide que un worker lance subagentes, además de `disallowedTools` | Pedir a `implementador` que lance un subagente | [ARCHITECTURE.md](ARCHITECTURE.md#invariantes) |
| 5 | Comportamiento ante timeout o caída de un worker | Interrumpir un worker en curso | [failure-modes.md](failure-modes.md) |
| 6 | ~~Compactación del contexto del router al excederse~~ Cerrado en 0.3.0 por diseño: el contador ya no depende del contexto, vive en el logbook `estado.md` y `orch-resume` lo reinyecta (ver #8 y [ADR 0010](decisions/0010-fuente-unica-logbook-y-backups.md)) | — | [failure-modes.md](failure-modes.md), [ARCHITECTURE.md](ARCHITECTURE.md#estado-y-memoria-entre-pasos) |
| 7 | Que el router clasifica en línea cuando la sesión es opus y lanza `clasificador` cuando no | Sesión con `/model sonnet` y una tarea no trivial | [routing.md](routing.md#paso-1-clasificar) |
| 8 | `[VERIFICAR]` Que Claude Code añade al contexto la salida de `orch-resume` en `SessionStart` con los matchers `compact` y `resume` | Tarea con logbook `estado.md` abierto; `/compact` y luego `claude --resume`; preguntar al router por `ciclos:` sin que relea el archivo | [ARCHITECTURE.md](ARCHITECTURE.md#estado-y-memoria-entre-pasos), [decisions/0010-fuente-unica-logbook-y-backups.md](decisions/0010-fuente-unica-logbook-y-backups.md) |
