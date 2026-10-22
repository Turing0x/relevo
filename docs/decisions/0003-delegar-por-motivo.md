# 0003 — Delegar por motivo, no por tamaño

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
La versión anterior delegaba toda implementación de ≤5 archivos a `implementador` (`~/.claude/backups/orch-review-1792228240/orchestrator/policy.md`, línea 15).

## Decisión
"Delegar solo por aislamiento de contexto (lectura ruidosa), revisión independiente o paralelismo real. Si no, en línea: un worker arranca en frío y pierde contexto" (`~/.claude/orchestrator/policy.md:7`). Umbral en línea: ≤2 archivos en mecánica e implementación, ≤3 archivos conocidos en búsqueda (`policy.md:27-30`).

## Alternativas
- Delegar por tamaño (versión anterior). Descartada por el coste del arranque en frío y la pérdida de contexto.

## Consecuencias
- Menos llamadas a workers en tareas pequeñas.
- El router hace más trabajo en línea con el modelo de la sesión; si el trabajo crece, reclasifica (`policy.md:17`).
