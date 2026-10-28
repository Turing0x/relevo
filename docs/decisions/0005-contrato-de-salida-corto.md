# 0005 — Contrato de salida corto con detalle en archivo

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
Los reportes de los workers ocupan contexto del router. Requisito de diseño: respuestas claras y concisas y un uso cuidadoso de la ventana de contexto.

## Decisión
Cada worker devuelve un reporte de ≤8 líneas (≤12 en `Explore`) con ESTADO, VEREDICTO o JSON. El detalle largo va a `.claude/work/` en la raíz git y solo viaja la ruta (`~/.claude/orchestrator/policy.md:41`). La consolidación final ocupa como máximo 4 líneas (`policy.md:63`; antes 6, `~/.claude/backups/orch-review-1792228240/orchestrator/policy.md` línea 41).

## Alternativas
- Reportes libres (versión anterior). Descartada por el consumo de contexto.

## Consecuencias
- `/orchestrator-init` debe añadir `.claude/work/` a `.gitignore` (`~/.claude/commands/orchestrator-init.md:8`).
- Sin repo git, el detalle va resumido en la salida (`policy.md:41`).
- Los proyectos activados antes de este cambio no tienen `.claude/work/` en `.gitignore` (ver [../failure-modes.md](../failure-modes.md)).
