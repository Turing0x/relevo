# 0004 — Verificación en dos gates e independencia por contexto

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
La versión anterior exigía que el verificador fuera un modelo distinto al implementador: si implementaba opus, verificaba sonnet (`~/.claude/backups/orch-review-1792228240/orchestrator/policy.md`, línea 33).

## Decisión
1. Gate determinista (test/lint/build) siempre que haya código; nunca `verificador` sobre rojo (`~/.claude/orchestrator/policy.md:47`).
2. `verificador` opus según el nivel de §5.2: 0 sin verificador, 1 foco, 2 completo ([0012](0012-verificacion-por-niveles.md)). La independencia viene del contexto limpio, "vale aunque implementara opus" (`policy.md:48`).
3. El verificador recibe la petición literal y nunca el razonamiento del implementador (`policy.md:53`).

## Alternativas
- Verificador de modelo distinto (versión anterior). Descartada: sonnet revisando a opus es más débil, y la prioridad es calidad sobre coste (ver [0002](0002-modelo-por-rol.md)).

## Consecuencias
- Los fallos baratos (tests) se detectan sin gastar opus.
- Cada tarea de riesgo medio o más cuesta al menos una llamada a opus.
- Actualización (ADR 0012): sustituye el disparador "riesgo medio+ o >1 archivo"; effort medium.
