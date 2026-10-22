# 0002 — Un modelo fijo por rol; opus como techo

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
Facturación por suscripción Max/Pro: lo que se optimiza es la cuota y la ventana de contexto, no los dólares (decisión del maintainer, 2026-10). Prioridad: calidad sobre coste, midiendo el coste por tarea completada.

## Decisión
| Worker | Modelo | effort | maxTurns |
|---|---|---|---|
| `clasificador`, `Explore`, `rapido` | haiku | low | 3 / 20 / 15 |
| `implementador` | sonnet | high | 40 |
| `arquitecto` | opus | xhigh | 30 |
| `verificador` | opus | high | 25 |

Fuente: `~/.claude/agents/*.md:4-6`. Fable 5.1 no entra en la escalera; opus es el techo (decisión del maintainer). `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` (`~/.claude/settings.json:4`) evita que los subagentes sin `model:` (p. ej. `general-purpose`) hereden opus ("tapar fugas de Opus").

## Alternativas
- Todo con el modelo de la sesión. Descartada: consume cuota de opus en búsquedas.
- Fable para `arquitecto`. Descartada (decisión del maintainer).
- Valores concretos de effort y maxTurns: `[VERIFICAR: elegidos por criterio, sin medición; revisar con /orch-stats]`.

## Consecuencias
- Haiku absorbe búsquedas y mecánica; opus solo en diseño y revisión.
- Los umbrales deben revisarse con datos de `/orch-stats` (`~/.claude/commands/orch-stats.md:6-10`).
