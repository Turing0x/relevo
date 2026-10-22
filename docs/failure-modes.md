# Modos de fallo

Este archivo cubre qué falla puede ocurrir en el orquestador, cómo se detecta, qué hace el sistema y qué debe hacer el humano. Los términos se definen en [GLOSSARY.md](GLOSSARY.md). Las rutas son absolutas desde `~/.claude/`.

"No especificado" significa que ni la política ni los hooks definen respuesta: el router improvisa. Esos casos están en [audit-pending.md](audit-pending.md).

| Fallo | Cómo se detecta | Qué hace el sistema | Qué debe hacer el humano |
|---|---|---|---|
| Timeout de un worker | No especificado | No especificado | Revisar `/tasks`; relanzar la tarea acotándola |
| Worker se cae o termina con error | No especificado; `orch-telemetry` registra la línea si hay transcript (`~/.claude/hooks/orch-telemetry:58-59`) | No especificado | Revisar el log y relanzar |
| Worker alcanza `maxTurns` | `/orch-stats`, columna `tope` (`~/.claude/orchestrator/stats.py`) | El worker se detiene `[VERIFICAR: qué devuelve al router]` | Si `tope` supera el 10 % de llamadas: subir `maxTurns` o partir tareas (`~/.claude/commands/orch-stats.md:7`) |
| Bucle implementar→verificar | Contador de ciclos en el contexto del router | Tras el 2º RECHAZADO: parar y reportar (`~/.claude/orchestrator/policy.md:34`) | Decidir: aceptar, replantear o autorizar más ciclos |
| Replan repetido | Llamadas a `arquitecto` en la tarea | Segunda llamada: AskUserQuestion; sin permiso, parar y reportar (`~/.claude/orchestrator/policy.md:19`, `:33`) | Autorizar o replantear la tarea |
| Gate determinista en rojo | Salida de test/lint/build | Vuelve al mismo ejecutor y cuenta como ciclo; nunca `verificador` (`~/.claude/orchestrator/policy.md:44`) | Nada, salvo que se agote el presupuesto |
| JSON del `clasificador` inválido | El router no puede parsearlo | El router clasifica en línea (`~/.claude/orchestrator/policy.md:10`) | Nada |
| Reporte de worker sin ESTADO/VEREDICTO | Telemetría `status: SIN_ESTADO` (`~/.claude/hooks/orch-telemetry:48-52`) | No especificado | Si es frecuente, revisar el prompt del agente (`~/.claude/commands/orch-stats.md:10`) |
| `verificador` sin `Causa` | El router la lee como dudosa | Re-brief al mismo ejecutor (`~/.claude/orchestrator/policy.md:20`) | Nada |
| `arquitecto` no puede entregar plan | Su contrato no tiene `ESCALAR` (`~/.claude/agents/arquitecto.md:15`) | No especificado | Aportar información o redefinir la tarea |
| Worker necesita archivos fuera del brief | `AMPLIAR` | Re-brief si sigue en alcance; si no, preguntar (`~/.claude/orchestrator/policy.md:16`) | Aprobar o rechazar la ampliación |
| `rapido` necesita ampliar | `rapido` no tiene `AMPLIAR` en su contrato (`~/.claude/agents/rapido.md:13`) | No especificado | — |
| Acción sensible detectada | `PENDIENTE_APROBACION` o el router la detecta | AskUserQuestion con acción, alcance y rollback (`~/.claude/orchestrator/policy.md:15`) | Aprobar o rechazar |
| Force push o borrado remoto de rama | Hook `block-force-push` (`~/.claude/hooks/block-force-push:40-43`) | Bloquea con exit 2 | Ejecutarlo a mano con `! git push ...` si es legítimo |
| Falso positivo de `block-force-push` | Un comando legítimo que contiene el texto "git push --force" (p. ej. en el patrón de un `grep`) se bloquea | Bloquea con exit 2 | Reescribir el comando sin ese texto |
| Acceso explícito a un secreto | Hook `guard-secrets` | Pide confirmación (`ask`) | Aprobar solo si es necesario |
| Falso positivo de `guard-secrets` | Patrones de búsqueda con nombres de secreto (`rg credentials src`) | Pide confirmación (`~/.claude/hooks/guard-secrets:7`) | Aprobar |
| Excepción interna de un hook | Ninguna (los hooks salen con 0) | `guard-secrets` y `block-force-push` dejan pasar la llamada (fail-open; `~/.claude/hooks/guard-secrets:73-74`, `~/.claude/hooks/block-force-push:38-39`) | — |
| Error de una tool dentro de un worker | No especificado en la política | El worker decide; si no lo resuelve, su reporte lo refleja | — |
| Contexto del router excedido | No especificado; no hay `autoCompactWindow` en ningún agente | Claude Code compacta según su configuración por defecto `[VERIFICAR]` | Abrir sesión nueva; el detalle en `.claude/work/` sobrevive |
| Planes o reportes en `.claude/work/` acaban en git | `.claude/work/` no está en `.gitignore` | Avisa y propone `/orchestrator-init` (`~/.claude/orchestrator/policy.md:41`) | Aprobar `/orchestrator-init` o añadirlo a mano |
| Agente de proyecto con nombre de worker | Existe `<repo>/.claude/agents/<worker>.md` | Avisa antes de usarlo (`~/.claude/orchestrator/policy.md:57`) | Decidir cuál usar |
| Copias de la tabla B desincronizadas | Revisión manual | No detectado | Editar `~/.claude/orchestrator/policy.md:23-30` y `~/.claude/agents/clasificador.md:17-22` a la vez |
| Config de proyecto intenta relajar la política | Lectura por el router | Se ignora (`~/.claude/orchestrator/policy.md:56`) | Corregir la config de proyecto |
