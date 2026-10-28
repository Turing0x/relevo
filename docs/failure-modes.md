# Modos de fallo

Este archivo cubre qué falla puede ocurrir en el orquestador, cómo se detecta, qué hace el sistema y qué debe hacer el humano. Los términos se definen en [GLOSSARY.md](GLOSSARY.md). Las rutas son absolutas desde `~/.claude/`.

"No especificado" significa que ni la política ni los hooks definen respuesta: el router improvisa. Esos casos están en [audit-pending.md](audit-pending.md).

| Fallo | Cómo se detecta | Qué hace el sistema | Qué debe hacer el humano |
|---|---|---|---|
| Timeout de un worker | No especificado | No especificado | Revisar `/tasks`; relanzar la tarea acotándola |
| Worker se cae o termina con error | No especificado; `orch-telemetry` registra la línea si hay transcript (`~/.claude/hooks/orch-telemetry:58-59`) | No especificado | Revisar el log y relanzar |
| Worker alcanza `maxTurns` | `/orch-stats`, columna `tope` (`~/.claude/orchestrator/stats.py`) | El worker se detiene `[VERIFICAR: qué devuelve al router]` | Si `tope` supera el 10 % de llamadas: subir `maxTurns` o partir tareas (`~/.claude/commands/orch-stats.md:7`) |
| Bucle implementar→verificar | Contador de ciclos en el contexto del router y en el logbook `estado.md` (`~/.claude/orchestrator/policy.md:38`) | Tras el 2º RECHAZADO: parar y reportar (`~/.claude/orchestrator/policy.md:36`) | Decidir: aceptar, replantear o autorizar más ciclos |
| Replan repetido | Llamadas a `arquitecto` en la tarea | Segunda llamada: AskUserQuestion; sin permiso, parar y reportar (`~/.claude/orchestrator/policy.md:19`, `:35`) | Autorizar o replantear la tarea |
| Gate determinista en rojo | Salida de test/lint/build | Vuelve al mismo ejecutor y cuenta como ciclo; nunca `verificador` (`~/.claude/orchestrator/policy.md:47`) | Nada, salvo que se agote el presupuesto |
| JSON del `clasificador` inválido | El router no puede parsearlo | El router clasifica en línea (`~/.claude/orchestrator/policy.md:10`) | Nada |
| Reporte de worker sin ESTADO/VEREDICTO | Telemetría `status: SIN_ESTADO` (`~/.claude/hooks/orch-telemetry:48-52`) | No especificado | Si es frecuente, revisar el prompt del agente (`~/.claude/commands/orch-stats.md:10`) |
| `verificador` sin `Causa` | El router la lee como dudosa | Re-brief al mismo ejecutor (`~/.claude/orchestrator/policy.md:20`) | Nada |
| `arquitecto` no puede entregar plan | Su contrato no tiene `ESCALAR` (`~/.claude/agents/arquitecto.md:15`) | No especificado | Aportar información o redefinir la tarea |
| Worker necesita archivos fuera del brief | `AMPLIAR` | Re-brief si sigue en alcance; si no, preguntar (`~/.claude/orchestrator/policy.md:16`) | Aprobar o rechazar la ampliación |
| `rapido` necesita ampliar | `rapido` no tiene `AMPLIAR` en su contrato (`~/.claude/agents/rapido.md:14`) | No especificado | — |
| Acción sensible detectada | `PENDIENTE_APROBACION` o el router la detecta | AskUserQuestion con acción, alcance y rollback (`~/.claude/orchestrator/policy.md:15`) | Aprobar o rechazar |
| Force push o borrado remoto de rama | Hook `block-force-push` (`~/.claude/hooks/block-force-push:40-43`) | Bloquea con exit 2 | Ejecutarlo a mano con `! git push ...` si es legítimo |
| Falso positivo de `block-force-push` | Un comando legítimo que contiene el texto "git push --force" (p. ej. en el patrón de un `grep`) se bloquea | Bloquea con exit 2 | Reescribir el comando sin ese texto |
| Acceso explícito a un secreto | Hook `guard-secrets` | Pide confirmación (`ask`) | Aprobar solo si es necesario |
| Falso positivo de `guard-secrets` | Patrones de búsqueda con nombres de secreto (`rg credentials src`) | Pide confirmación (`~/.claude/hooks/guard-secrets:7`) | Aprobar |
| Excepción interna de un hook | Ninguna (los hooks salen con 0) | `guard-secrets` y `block-force-push` dejan pasar la llamada (fail-open; `~/.claude/hooks/guard-secrets:73-74`, `~/.claude/hooks/block-force-push:38-39`) | — |
| Error de una tool dentro de un worker | No especificado en la política | El worker decide; si no lo resuelve, su reporte lo refleja | — |
| Contexto del router excedido | No especificado; no hay `autoCompactWindow` en ningún agente | Claude Code compacta según su configuración por defecto; el hook `orch-resume` (`SessionStart` `compact`) imprime el logbook activo y sus contadores mandan sobre la memoria del chat (`~/.claude/orchestrator/policy.md:38`) `[VERIFICAR: que la salida llega al contexto]` | Si el router no recuerda contadores, pedirle que lea `.claude/work/<tarea>/estado.md` |
| Sesión reanudada (`--resume`) con tarea a medias | Hook `orch-resume` (`SessionStart` `resume`) | Imprime el `estado.md` más reciente sin `estado: cerrada` y lista las otras tareas abiertas | Cerrar con `estado: cerrada` los logbooks abandonados |
| Logbook en un repo sin `.claude/work/` en `.gitignore` | `orch-resume` | No reinyecta el contenido (un repo clonado podría traer un `estado.md` con instrucciones); imprime un aviso y propone `/orchestrator-init` | Aprobar `/orchestrator-init` o añadir `.claude/work/` al `.gitignore` |
| Excepción interna de `orch-resume` | Ninguna (sale con 0) | No imprime nada; la sesión sigue sin logbook | Leer `estado.md` a mano |
| Planes o reportes en `.claude/work/` acaban en git | `.claude/work/` no está en `.gitignore` | Avisa y propone `/orchestrator-init` (`~/.claude/orchestrator/policy.md:44`) | Aprobar `/orchestrator-init` o añadirlo a mano |
| Agente de proyecto con nombre de worker | Existe `<repo>/.claude/agents/<worker>.md` | Avisa antes de usarlo (`~/.claude/orchestrator/policy.md:70`) | Decidir cuál usar |
| Copias de la tabla B desincronizadas | `scripts/render_routing.py --check` en `make docs-check` (CI Docs) y `tests/test_repo_consistency.py` (`PolicySyncTests`) | CI en rojo | En el repo: editar `orchestrator/routing.json`, ejecutar `python3 scripts/render_routing.py` y reinstalar; no editar a mano el texto entre `<!-- relevo:routing:begin -->` y `<!-- relevo:routing:end -->` (`~/.claude/orchestrator/policy.md:24-32`, `~/.claude/agents/clasificador.md:18-24`) |
| Lista de alto riesgo distinta en `clasificador` | `tests/test_repo_consistency.py` (`PolicySyncTests`) | CI en rojo | Editar `~/.claude/orchestrator/policy.md:56-62` y `~/.claude/agents/clasificador.md:25-31` a la vez |
| Worker sin línea `Riesgo:` o con formato inválido | Lectura del reporte por el router | Riesgo mínimo medio → `verificador` (`~/.claude/orchestrator/policy.md:63`) | Si es frecuente, revisar el prompt del agente |
| Worker declara `Riesgo: ninguno` pero el diff toca un elemento | `verificador` (contexto limpio) o comprobación del router | El riesgo final usa el máximo con el juicio del router (`~/.claude/orchestrator/policy.md:11`) | Nada |
| La línea `Riesgo:` sube el riesgo tras un cambio en línea | Línea `Riesgo:` del trabajo en línea | Reaplicar tabla B y verificación (`~/.claude/orchestrator/policy.md:11`) | Nada |
| El comando re-ejecutado por el router no da el resultado reportado | Comprobación del router (`~/.claude/orchestrator/policy.md:50`) | Cuenta como gate determinista en rojo | Nada, salvo que se agote el presupuesto |
| La cita `archivo:línea` de `Explore` no coincide | Comprobación del router (`~/.claude/orchestrator/policy.md:50`) | `Explore` insuficiente → seguir en línea (`~/.claude/orchestrator/policy.md:17`) | Nada |
| Hallazgo nuevo en recheck | `verificador` en `modo: recheck` lo marca como advertencia (`~/.claude/agents/verificador.md:15`) | No consume ciclo; sale en la consolidación final como pendiente (`~/.claude/orchestrator/policy.md:36`, `:66`) | Decidir si se corrige |
| Defecto que ya existía en la base | `verificador` lo reproduce en `base_commit` | Advertencia, no bloqueante (`~/.claude/agents/verificador.md:13`) | Decidir si se abre tarea aparte |
| Brief sin `base_commit` para `verificador` | Lectura del brief | No especificado `[VERIFICAR]`; sin base no puede separar bloqueante de preexistente | Pasar `git rev-parse HEAD` previo al cambio |
| El router no puede derivar la superficie permitida | Al preparar el brief | AskUserQuestion con rutas candidatas antes de lanzar (`~/.claude/orchestrator/policy.md:42`) | Aprobar o corregir la lista |
| Prompt bloqueante sin UI interactiva | AskUserQuestion no disponible | Mostrar el texto completo con todas las opciones y parar (`~/.claude/orchestrator/policy.md:15`) | Responder en el chat |
| `settings.json` con comentarios (JSONC) o claves duplicadas | El instalador al leerlo | Falla sin escribir nada: reescribirlo como JSON perdería los comentarios o una de las claves (`scripts/relevo_install.py`, `parse_settings`) | Quitar comentarios o duplicados, o instalar con `--no-settings` y fusionar a mano |
| Demasiadas copias de seguridad | `<prefix>/.relevo-backups/` | Una copia idéntica a otra se reutiliza (checksum); se conservan las 5 usadas más recientemente, las fijadas y las que guardan un original de `--force` | Fijar una copia con `relevo_install.py backups --pin <nombre>` o `install --pin-backup` |
| Config de proyecto intenta relajar la política | Lectura por el router | Se ignora (`~/.claude/orchestrator/policy.md:69`) | Corregir la config de proyecto |
