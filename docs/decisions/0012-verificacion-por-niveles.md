# 0012 — Verificación por niveles y tope de effort `medium`

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
El `verificador` consumía ≈240 min, el 26 % del tiempo de workers (63 llamadas en 15 días por `agent_id` único con su última fila, log anterior a 2026-11-05 10:58:09, mediana 160 s; la suma de tiempo y el porcentaje excluyen ejecuciones de más de 3 h: 2 de `verificador` y 5 de `implementador`), y repetía la suite que el gate determinista ya había pasado (17 % de su tiempo). El disparador "riesgo medio+ o >1 archivo" no distinguía un renombrado de un rediseño.

Rechazos en primera revisión: 38 %; en recheck: 17 %. Por líneas del diff:

| Líneas | Rechazadas |
|---|---|
| ≤50 | 0/4 |
| 51-200 | 3/9 |
| 201-600 | 7/13 |
| >600 | 5/11 |
| sin stat | 4/13 |

Muestra pequeña; líneas tomadas del `git diff --stat` del propio verificador. Sirve para orientar los cortes, no para probarlos.

## Decisión
Tres niveles decididos con el diff real tras el gate 1 en verde (`~/.claude/orchestrator/policy.md:48-54`):
- **Nivel 0, sin verificador:** riesgo final bajo y sin cambio de comportamiento, o ≤50 líneas de producción cubiertas por un test. Lo decide el router leyendo el diff y consta en §7.
- **Nivel 1, foco:** ≤200 líneas y ≤5 archivos de producción, sin riesgo alto. Diff, criterios y llamadores directos, ~12 turnos.
- **Nivel 2, completo:** riesgo alto, >200 líneas o >5 archivos de producción, salida de `arquitecto`, replan, ruta "verificador obligatorio" o tarea `revision`. Es la revisión anterior.

Además: el verificador recibe el resultado del gate 1 y no repite la suite; §5.3 se omite si el router ya ejecutó ese comando sobre el mismo estado; en multitramo, gate 1 por tramo, verificador en tramos de riesgo alto y nivel 2 al final; las docs que actúan como código son nivel 1 como mínimo; el recheck no cambia. La telemetría guarda `nivel` y `motivo` (slug) y `/orch-stats` muestra la mediana de duración.

**Effort (decisión del usuario):** tope `medium` para todo worker. `verificador` y `arquitecto`: opus medium. `implementador`: sonnet medium. `clasificador`, `Explore`, `rapido`: low. Lo comprueba `tests/test_repo_consistency.py` (`EffortCapTests`).

## Relación con ADR 0009
[0009](0009-riesgo-declarado-y-recheck.md) dice "solo se añaden reglas; ninguna se relaja". Describía aquel cambio, no una prohibición futura. Este ADR **sí relaja**, por decisión explícita del usuario: un cambio de riesgo bajo con más de un archivo deja de disparar la revisión, y el nivel 1 revisa menos que antes. Lo que 0009 descartó, un verificador solo en alto riesgo porque dejaba sin revisar el riesgo medio, sigue descartado: el riesgo medio siempre tiene al menos nivel 1. El "cada tarea de riesgo medio o más cuesta al menos una llamada a opus" de [0004](0004-verificacion-dos-gates.md) sigue siendo cierto.

## Alternativas
- Verificador solo en riesgo alto. Descartada: ver arriba.
- Bajar el verificador a sonnet. Descartada: la independencia viene del contexto, y sonnet revisando a opus es más débil ([0004](0004-verificacion-dos-gates.md)).
- Mantener el disparador y solo limitar turnos. Descartada: seguiría gastando opus en cambios sin comportamiento.
- Un `maxTurns` por nivel. No es posible: es un valor por agente; "~12 turnos" es presupuesto de prompt.

## Consecuencias
- Ahorro estimado del 20-35 % del tiempo de verificación. No medido; revisar con `/orch-stats` a los 30 días, comparando rechazos por nivel.
- **Un defecto en nivel 0 no lo ve nadie salvo los tests.** Por eso exige riesgo final bajo y cobertura; no hay enforcement: es texto de política ([0001](0001-politica-con-refuerzo-duro.md)).
- El nivel 0 no lanza worker y por tanto no deja línea en `log.jsonl`: `/orch-stats` no puede contar cuántas veces se omitió la revisión. Solo consta en la consolidación final.
- El verificador deja de ser una segunda ejecución de la suite: depende de que el router haya pasado el gate 1 de verdad.
- Effort `medium` en `arquitecto` y `implementador` no está medido. Si sube `RECHAZADO` o `ESCALAR`, la vía es partir tareas o mejorar briefs; subir el effort requiere otro ADR.
- `[VERIFICAR]` que ninguna variable de entorno de Claude Code pise el `effort` del frontmatter; el campo `effort` de `log.jsonl` lo mostraría.
