# 0007 — Presupuesto: 1 arquitecto y 2 ciclos por tarea

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
Sin límites, los ciclos implementar→verificar y los replan pueden no terminar.

## Decisión
Máximo 1 llamada a `arquitecto` por tarea, incluido el replan, y 2 ciclos. Todo RECHAZADO cuenta y el replan no reinicia el contador. Agotado el presupuesto: parar y reportar o preguntar (`~/.claude/orchestrator/policy.md:35-36`, `:19`). Viene de la versión anterior (`~/.claude/backups/orch-review-1792228240/orchestrator/policy.md`, líneas 22-23).

## Por qué
`[VERIFICAR: no hay registro del motivo de los valores 1 y 2]`.

## Alternativas
`[VERIFICAR]`

## Consecuencias
- Las tareas difíciles vuelven al usuario en vez de consumir cuota sin fin.
- El contador vive solo en el contexto del router; no hay enforcement (ver [0001-politica-con-refuerzo-duro.md](0001-politica-con-refuerzo-duro.md)).
