# Documentación del orquestador de agentes

Punto de entrada. Explica qué es el orquestador, qué contiene cada archivo de esta carpeta y en qué orden leerlos. Las rutas de código son absolutas desde `~/.claude/`.

## Qué es

El orquestador es una política en lenguaje natural (`~/.claude/orchestrator/policy.md`) que la sesión principal de Claude Code carga en cada sesión y aplica como router. Reparte cada tarea entre trabajo en línea y seis workers (haiku, sonnet, opus) según su tipo. Permisos y hooks de Claude Code imponen lo crítico para la seguridad; el resto depende de que el modelo obedezca la política.

## Archivos

| Archivo | Contiene | Léelo cuando |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Propósito, cuándo no delegar, componentes, diagrama, recorrido de una tarea, invariantes (impuestos o solo de política), estado | Necesites el modelo mental completo |
| [GLOSSARY.md](GLOSSARY.md) | Definición de cada término con su ubicación en el código | Un término no esté claro |
| [routing.md](routing.md) | Tablas de decisión: clasificación, tabla A, tabla B, verificación, escalado, presupuesto, casos sin regla | Quieras saber quién ejecuta algo y con qué modelo |
| [agents/clasificador.md](agents/clasificador.md) | Ficha de `clasificador` (haiku) | — |
| [agents/Explore.md](agents/Explore.md) | Ficha de `Explore` (haiku) | — |
| [agents/rapido.md](agents/rapido.md) | Ficha de `rapido` (haiku) | — |
| [agents/implementador.md](agents/implementador.md) | Ficha de `implementador` (sonnet) | — |
| [agents/arquitecto.md](agents/arquitecto.md) | Ficha de `arquitecto` (opus) | — |
| [agents/verificador.md](agents/verificador.md) | Ficha de `verificador` (opus) | — |
| [contracts/brief.schema.json](contracts/brief.schema.json) | Brief router → worker | Escribas o valides un brief |
| [contracts/clasificador-output.schema.json](contracts/clasificador-output.schema.json) | JSON de `clasificador` | — |
| [contracts/explore-output.schema.json](contracts/explore-output.schema.json) | Reporte de `Explore` | — |
| [contracts/rapido-output.schema.json](contracts/rapido-output.schema.json) | Reporte de `rapido` | — |
| [contracts/implementador-output.schema.json](contracts/implementador-output.schema.json) | Reporte de `implementador` | — |
| [contracts/arquitecto-output.schema.json](contracts/arquitecto-output.schema.json) | Reporte de `arquitecto` | — |
| [contracts/verificador-output.schema.json](contracts/verificador-output.schema.json) | Reporte de `verificador` | — |
| [contracts/telemetry-record.schema.json](contracts/telemetry-record.schema.json) | Línea de `log.jsonl` | Analices la telemetría |
| [failure-modes.md](failure-modes.md) | Fallos, detección, respuesta del sistema y del humano | Algo salga mal |
| [examples/implementacion-con-rechazo.md](examples/implementacion-con-rechazo.md) | Recorrido con `implementador`, gates y un `RECHAZADO` | Quieras ver el flujo completo |
| [examples/busqueda-amplia.md](examples/busqueda-amplia.md) | Recorrido con `Explore` y trabajo en línea | — |
| [examples/accion-sensible.md](examples/accion-sensible.md) | Recorrido con aprobación humana, permisos y hooks | — |
| [decisions/0001-politica-con-refuerzo-duro.md](decisions/0001-politica-con-refuerzo-duro.md) | Por qué texto + hooks y no código | Quieras cambiar el diseño |
| [decisions/0002-modelo-por-rol.md](decisions/0002-modelo-por-rol.md) | Modelo, effort y maxTurns por worker | — |
| [decisions/0003-delegar-por-motivo.md](decisions/0003-delegar-por-motivo.md) | Delegar solo con motivo; umbrales en línea | — |
| [decisions/0004-verificacion-dos-gates.md](decisions/0004-verificacion-dos-gates.md) | Gate determinista + `verificador` opus | — |
| [decisions/0005-contrato-de-salida-corto.md](decisions/0005-contrato-de-salida-corto.md) | Reportes cortos y `.claude/work/` | — |
| [decisions/0006-telemetria-por-hook.md](decisions/0006-telemetria-por-hook.md) | Hook `orch-telemetry` y `/orch-stats` | — |
| [decisions/0007-presupuesto.md](decisions/0007-presupuesto.md) | 1 `arquitecto` y 2 ciclos por tarea | — |
| [decisions/0008-guard-secrets-ask.md](decisions/0008-guard-secrets-ask.md) | Hook `guard-secrets` con `ask` | — |
| [audit-pending.md](audit-pending.md) | Comprobaciones en ejecución pendientes (`[VERIFICAR]`) | Hagas la auditoría |

## Orden de lectura recomendado

1. Este archivo.
2. [GLOSSARY.md](GLOSSARY.md).
3. [ARCHITECTURE.md](ARCHITECTURE.md).
4. [routing.md](routing.md).
5. La ficha del agente que te interese en `agents/`.
6. [failure-modes.md](failure-modes.md).
7. Un ejemplo de `examples/`.
8. `decisions/` y [audit-pending.md](audit-pending.md) si vas a cambiar el sistema.

## Fuera de alcance

No se documentan: hooks, servidores MCP, plugins y sus agentes que el usuario tenga instalados por su cuenta ni los integrados de Claude Code (`general-purpose`, `Plan`, `claude-code-guide`, `statusline-setup`). Única relación: los subagentes sin `model:` usan sonnet por `CLAUDE_CODE_SUBAGENT_MODEL` (`~/.claude/settings.json:4`). Las instrucciones operativas están en `~/.claude/CLAUDE.md` y `~/.claude/orchestrator/policy.md`; esta carpeta las describe sin copiarlas.
