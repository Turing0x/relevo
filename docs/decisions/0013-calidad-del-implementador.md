# 0013 — Calidad del código del `implementador`

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
El prompt del `implementador` no decía nada de calidad y el `verificador` tiene prohibido el estilo (precision gate, `~/.claude/agents/verificador.md:14`). Telemetría de `log.jsonl` a 2026-11-05 (corridas de `implementador` con transcript y ≤3 h, por `agent_id` único): 203 de 377 ejecuciones de tests repiten un comando idéntico (algunas repeticiones son legítimas tras un arreglo); el 16 % del tiempo se va en tests; 9 de 72 corridas llegaron a ≥40 turnos.

Auditoría de 15 diffs reales, 13 cambios independientes (2 duplicados por snapshots):

| Hallazgo | Cambios |
|---|---|
| Duplicación dentro del diff | 8/13 |
| Sobreingeniería | 7/13 (9/13 con dudosos) |
| Código huérfano o muerto | 5/13 |
| Comentarios innecesarios | 4/13 (12 casos frente a ~66 útiles, estimación a mano) |
| Tests sobredimensionados | 3/13 |
| Complejidad algorítmica evitable | 2/13 firmes (trabajo repetido); O(n²) sobre colecciones sin límite: no observado |

Límites de la muestra: la autoría no está garantizada (commits hasta 2 h tras una corrida, pueden incluir trabajo del router, algunos son snapshots); casi toda es de effort high; la regla de pasos no se evaluó con diffs, se apoya en la telemetría.

## Decisión
- Cinco reglas en `~/.claude/agents/implementador.md:12-16`: Simplicidad, Comentarios, Eficiencia, Pasos y Repaso final. `model`, `effort` y `maxTurns` no cambian.
- El `verificador` de nivel 2 avisa también de complejidad evitable visible en el diff (trabajo repetido, sobreingeniería, código huérfano): siempre `[advertencia]`, nunca bloqueante y sin comandos extra (`~/.claude/agents/verificador.md:16`). No contradice el precision gate: sigue exigiendo evidencia.
- `tests/test_repo_consistency.py` (`ImplementerQualityTests`) exige las cinco etiquetas y el aviso.

## Alternativas
- Regla de comentarios "solo el porqué". Descartada: borraría comentarios útiles como el significado de valores especiales.
- Aviso del `verificador` bloqueante. Descartada: volvería a alargar la revisión.

## Consecuencias
- Sin enforcement: es texto de prompt ([0001](0001-politica-con-refuerzo-duro.md)).
- Revisar a los 30 días comparando comandos repetidos y turnos en `log.jsonl`.
- Las referencias a la tarea en asuntos de commit quedan fuera de estas reglas.
- `[VERIFICAR]` que las reglas mejoran el resultado: no medido.
