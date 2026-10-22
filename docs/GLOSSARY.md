# Glosario

Este archivo define cada término de la documentación del orquestador. Cada término tiene un único significado y se usa siempre igual. Las rutas son absolutas desde `~/.claude/`.

| Término | Definición | Dónde aparece en el código |
|---|---|---|
| orquestador | Sistema formado por la política, seis workers, tres hooks, permisos y dos comandos que reparte el trabajo de una sesión de Claude Code entre modelos. No es un programa: la política la interpreta el modelo de la sesión. | `~/.claude/orchestrator/policy.md`, `~/.claude/CLAUDE.md:6` |
| política | Texto en lenguaje natural con las reglas del orquestador. Se carga en cada sesión vía `@orchestrator/policy.md`. | `~/.claude/orchestrator/policy.md` |
| router | La sesión principal de Claude Code cuando aplica la política: clasifica, elige ruta, lanza workers y consolida. | `~/.claude/orchestrator/policy.md:4` |
| worker | Subagente de Claude Code definido por el orquestador en `~/.claude/agents/`: `clasificador`, `Explore`, `rapido`, `implementador`, `arquitecto`, `verificador`. | `~/.claude/agents/*.md` |
| subagente | Mecanismo de Claude Code: instancia aislada con contexto propio lanzada con la herramienta `Agent`. Todo worker es un subagente; no todo subagente es un worker. | `~/.claude/settings.json:3` |
| en línea | Ejecución por el router mismo, sin lanzar worker. | `~/.claude/orchestrator/policy.md:7`, `:24-30` |
| aislamiento de contexto | Motivo para delegar: la lectura es ruidosa (búsqueda amplia, logs, salida de tests) y conviene que no llene el contexto del router. | `~/.claude/orchestrator/policy.md:7` |
| brief | Mensaje autocontenido que el router envía a un worker: objetivo, archivos permitidos, criterios de aceptación, comando de verificación, límites y ruta del plan si existe. | `~/.claude/orchestrator/policy.md:39` |
| tipo | Categoría de la tarea: `busqueda`, `mecanica`, `implementacion`, `arquitectura`, `bug_dificil`, `revision`. | `~/.claude/agents/clasificador.md:12`, `:16` |
| riesgo | `bajo`, `medio` o `alto`. Alto si toca auth, pagos, migraciones/DB, secretos, infra/deploy, borrado masivo, git push/force, dependencias, envío de mensajes o rutas sensibles del proyecto. | `~/.claude/agents/clasificador.md:13`, `:23-25` |
| riesgo final | Máximo entre el riesgo del `clasificador`, el juicio del router y los disparadores de acción sensible. Es el que usa la tabla B. | `~/.claude/orchestrator/policy.md:11` |
| complejidad | Entero de 1 a 5 estimado al clasificar. | `~/.claude/agents/clasificador.md:13` |
| ruta | Destino de una tarea: `en_linea`, `Explore`, `rapido`, `implementador`, `arquitecto` o `verificador`. | `~/.claude/agents/clasificador.md:14` |
| tabla A | Reglas del router para acciones sensibles y respuestas de worker. Tiene prioridad sobre la tabla B. | `~/.claude/orchestrator/policy.md:14-21` |
| tabla B | Ruta inicial por tipo. Hay una copia en `clasificador`. | `~/.claude/orchestrator/policy.md:23-30`, `~/.claude/agents/clasificador.md:17-22` |
| plan | Archivo `.claude/work/plan-<tarea>.md` escrito por `arquitecto` con diagnóstico o diseño dividido en tramos. | `~/.claude/agents/arquitecto.md:13` |
| tramo | Parte de un plan que se encarga a un `implementador`, con archivos, criterios y verificación propios. | `~/.claude/agents/arquitecto.md:11` |
| replan | Nueva llamada a `arquitecto` con los hallazgos tras ESCALAR de `implementador` o RECHAZADO con `Causa: diseño`. | `~/.claude/orchestrator/policy.md:19` |
| ciclo | Una iteración implementar→verificar. Cuenta todo RECHAZADO y todo gate determinista en rojo. | `~/.claude/orchestrator/policy.md:34`, `:44` |
| presupuesto | Límites por tarea: 1 llamada a `arquitecto`, 2 ciclos, `maxTurns` por llamada. | `~/.claude/orchestrator/policy.md:32-36` |
| gate determinista | Primer paso de verificación: test/lint/build del proyecto. | `~/.claude/orchestrator/policy.md:44` |
| verificación independiente | Segundo paso de verificación: `verificador` con contexto limpio, si el riesgo es medio o alto o cambió más de un archivo. | `~/.claude/orchestrator/policy.md:45-46` |
| acción sensible | Acción que exige aprobación humana: push/force/reset --hard/branch -D, deploy, migraciones/SQL destructivo, borrado recursivo, secretos, dependencias, IAM/infra/DNS, mensajes externos, pagos. | `~/.claude/orchestrator/policy.md:49` |
| refuerzo duro | Mecanismo que Claude Code aplica sin depender del modelo: `permissions.ask`/`deny` y hooks. | `~/.claude/orchestrator/policy.md:50`, `~/.claude/settings.json:7-90` |
| contrato de salida | Formato del reporte final de cada worker: ESTADO, VEREDICTO o JSON. | `~/.claude/orchestrator/policy.md:41` |
| ESTADO | Primera línea del reporte de `rapido`, `implementador` y `arquitecto`: `OK`, `ESCALAR`, `AMPLIAR` o `PENDIENTE_APROBACION`. | `~/.claude/agents/implementador.md:15` |
| OK | Valor de ESTADO: el worker terminó lo encargado. | `~/.claude/agents/implementador.md:15` |
| ESCALAR | Valor de ESTADO: la tarea excede al worker (necesita diseño). | `~/.claude/agents/implementador.md:13` |
| AMPLIAR | Valor de ESTADO: el worker necesita archivos fuera del brief. | `~/.claude/agents/implementador.md:10` |
| PENDIENTE_APROBACION | Valor de ESTADO: el worker detectó una acción sensible y no la ejecutó. | `~/.claude/orchestrator/policy.md:40` |
| VEREDICTO | Primera línea del reporte de `verificador`: `APROBADO` o `RECHAZADO`. | `~/.claude/agents/verificador.md:14` |
| Causa | Segunda línea del reporte de `verificador`: `diseño`, `implementación` o `—`. | `~/.claude/agents/verificador.md:15` |
| consolidación final | Respuesta del router al usuario al cerrar la tarea, máx. 4 líneas. | `~/.claude/orchestrator/policy.md:53` |
| config de proyecto | Archivo `.claude/orchestrator.md` de un repo. Solo puede endurecer la política. | `~/.claude/orchestrator/policy.md:56`, `~/.claude/orchestrator/project-template.md` |
| `.claude/work/` | Carpeta en la raíz git del proyecto donde los workers escriben planes y reportes largos. | `~/.claude/orchestrator/policy.md:41` |
| telemetría | Registro de métricas por worker en `~/.claude/orchestrator/log.jsonl`, escrito por el hook `orch-telemetry`. | `~/.claude/hooks/orch-telemetry` |
| `SIN_ESTADO` | Valor de `status` en telemetría cuando el reporte no contiene ESTADO, VEREDICTO ni JSON. | `~/.claude/hooks/orch-telemetry:48-52` |
| effort | Nivel de razonamiento del modelo por worker: `low`, `medium`, `high`, `xhigh`, `max`. | `~/.claude/agents/*.md:5` |
| `maxTurns` | Tope de turnos de un worker por llamada. | `~/.claude/agents/*.md:6` |
