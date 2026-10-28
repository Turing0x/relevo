# Glosario

Este archivo define cada término de la documentación del orquestador. Cada término tiene un único significado y se usa siempre igual. Las rutas son absolutas desde `~/.claude/`.

| Término | Definición | Dónde aparece en el código |
|---|---|---|
| orquestador | Sistema formado por la política, seis workers, cuatro hooks, permisos y dos comandos que reparte el trabajo de una sesión de Claude Code entre modelos. No es un programa: la política la interpreta el modelo de la sesión. | `~/.claude/orchestrator/policy.md`, `~/.claude/CLAUDE.md:6` |
| política | Texto en lenguaje natural con las reglas del orquestador. Se carga en cada sesión vía `@orchestrator/policy.md`. | `~/.claude/orchestrator/policy.md` |
| router | La sesión principal de Claude Code cuando aplica la política: clasifica, elige ruta, lanza workers y consolida. | `~/.claude/orchestrator/policy.md:4` |
| worker | Subagente de Claude Code definido por el orquestador en `~/.claude/agents/`: `clasificador`, `Explore`, `rapido`, `implementador`, `arquitecto`, `verificador`. | `~/.claude/agents/*.md` |
| subagente | Mecanismo de Claude Code: instancia aislada con contexto propio lanzada con la herramienta `Agent`. Todo worker es un subagente; no todo subagente es un worker. | `~/.claude/settings.json:3` |
| en línea | Ejecución por el router mismo, sin lanzar worker. | `~/.claude/orchestrator/policy.md:7`, `:25-31` |
| aislamiento de contexto | Motivo para delegar: la lectura es ruidosa (búsqueda amplia, logs, salida de tests) y conviene que no llene el contexto del router. | `~/.claude/orchestrator/policy.md:7` |
| brief | Mensaje autocontenido que el router envía a un worker: objetivo, superficie permitida, criterios de aceptación, comando de verificación, límites y ruta del plan si existe; para `verificador`, además `base_commit`, `modo` y, en recheck, `recheck_findings`. | `~/.claude/orchestrator/policy.md:42`, `:49` |
| superficie permitida | Sección `## Superficie permitida` del brief: rutas o globs estrechos relativos a la raíz git, nunca `.` ni rutas absolutas. Si el router no puede derivarla, pregunta con candidatos. | `~/.claude/orchestrator/policy.md:42` |
| tipo | Categoría de la tarea: `busqueda`, `mecanica`, `implementacion`, `arquitectura`, `bug_dificil`, `revision`. | `~/.claude/agents/clasificador.md:12`, `:16` |
| riesgo | `bajo`, `medio` o `alto`. Alto si toca un elemento 1-5 de la lista de alto riesgo o rutas sensibles del proyecto; el elemento 6 lo deja en medio como mínimo. | `~/.claude/agents/clasificador.md:13`, `:25-33` |
| lista de alto riesgo | Seis elementos numerados (§6bis): 1 datos o efectos irreversibles, 2 seguridad, 3 contratos consumidos por otros, 4 concurrencia, 5 entrega/entorno/dependencias, 6 ningún test detectaría una regresión. Copia con los mismos números en `clasificador`. | `~/.claude/orchestrator/policy.md:56-63`, `~/.claude/agents/clasificador.md:25-31` |
| línea de riesgo | Línea obligatoria `Riesgo: <N>[,<N>] (<motivo>) \| ninguno` al final del reporte de `implementador`, `rapido` y del trabajo en línea con cambios. Entra en el riesgo final. | `~/.claude/orchestrator/policy.md:63`, `~/.claude/agents/implementador.md:20`, `~/.claude/agents/rapido.md:16` |
| riesgo final | Máximo entre el riesgo del `clasificador`, el juicio del router, los disparadores de acción sensible, los elementos de la lista de alto riesgo y la línea de riesgo del worker. Es el que usa la tabla B. | `~/.claude/orchestrator/policy.md:11` |
| complejidad | Entero de 1 a 5 estimado al clasificar. | `~/.claude/agents/clasificador.md:13` |
| ruta | Destino de una tarea: `en_linea`, `Explore`, `rapido`, `implementador`, `arquitecto` o `verificador`. | `~/.claude/agents/clasificador.md:14` |
| tabla A | Reglas del router para acciones sensibles y respuestas de worker. Tiene prioridad sobre la tabla B. | `~/.claude/orchestrator/policy.md:14-21` |
| tabla B | Ruta inicial por tipo. Se genera desde `orchestrator/routing.json` del repo; hay una copia en `clasificador`. | `~/.claude/orchestrator/policy.md:23-31`, `~/.claude/agents/clasificador.md:17-23` |
| fuente única de la tabla B | `orchestrator/routing.json` del repo: filas y umbrales de la tabla B. `scripts/render_routing.py` reescribe el texto entre `<!-- relevo:routing:begin -->` y `<!-- relevo:routing:end -->` en la política y en `clasificador`; con `--check` (en `make docs-check`) falla si no coinciden. | `orchestrator/routing.json`, `scripts/render_routing.py` |
| plan | Archivo `.claude/work/plan-<tarea>.md` escrito por `arquitecto` con diagnóstico o diseño dividido en tramos. | `~/.claude/agents/arquitecto.md:13` |
| tramo | Parte de un plan que se encarga a un `implementador`, con archivos, criterios y verificación propios. | `~/.claude/agents/arquitecto.md:11` |
| replan | Nueva llamada a `arquitecto` con los hallazgos tras ESCALAR de `implementador` o RECHAZADO con `Causa: diseño`. | `~/.claude/orchestrator/policy.md:19` |
| ciclo | Una iteración implementar→verificar. Cuenta todo RECHAZADO y todo gate determinista en rojo. | `~/.claude/orchestrator/policy.md:36`, `:47` |
| recheck | Modo del `verificador` en el 2º ciclo tras RECHAZADO con `Causa: implementación` o dudosa: revisa solo los hallazgos previos (`recheck_findings`); un hallazgo nuevo es advertencia y no consume ciclo. | `~/.claude/orchestrator/policy.md:36`, `~/.claude/agents/verificador.md:15` |
| bloqueante | Hallazgo del `verificador` causado por el cambio y no reproducible en `base_commit`. Solo un bloqueante produce RECHAZADO; el resto es advertencia. | `~/.claude/agents/verificador.md:13` |
| logbook | Archivo `<raíz git>/.claude/work/<tarea>/estado.md` con el estado de una tarea: petición literal, ruta, `arquitecto: N/1`, `ciclos: N/2`, tramos, último veredicto y siguiente paso. Se crea si la tarea usa `arquitecto`, tiene más de un tramo o no se puede retomar solo con la petición y el diff; se cierra con `estado: cerrada`. Tras compactar o reanudar, sus contadores mandan. | `~/.claude/orchestrator/policy.md:38` |
| `orch-resume` | Hook de `SessionStart` (matchers `compact` y `resume`, timeout 5 s) que imprime el logbook abierto más reciente de la raíz git. Solo lectura; nunca bloquea; no reinyecta nada si `.claude/work/` no está en `.gitignore`. | `~/.claude/hooks/orch-resume` |
| presupuesto | Límites por tarea: 1 llamada a `arquitecto`, 2 ciclos, `maxTurns` por llamada. | `~/.claude/orchestrator/policy.md:34-39` |
| gate determinista | Primer paso de verificación: test/lint/build del proyecto. | `~/.claude/orchestrator/policy.md:47` |
| verificación independiente | Segundo paso de verificación: `verificador` con contexto limpio, si el riesgo es medio o alto o cambió más de un archivo. | `~/.claude/orchestrator/policy.md:48-49` |
| comprobación del router | Antes de la consolidación final, el router re-ejecuta 1 comando reportado por un worker y abre 1 cita `archivo:línea` de `Explore`. | `~/.claude/orchestrator/policy.md:50` |
| acción sensible | Acción que exige aprobación humana: push/force/reset --hard/branch -D, deploy, migraciones/SQL destructivo, borrado recursivo, secretos, dependencias, IAM/infra/DNS, mensajes externos, pagos. | `~/.claude/orchestrator/policy.md:53` |
| refuerzo duro | Mecanismo que Claude Code aplica sin depender del modelo: `permissions.ask`/`deny` y hooks. | `~/.claude/orchestrator/policy.md:54`, `~/.claude/settings.json:7-90` |
| contrato de salida | Formato del reporte final de cada worker: ESTADO, VEREDICTO o JSON. | `~/.claude/orchestrator/policy.md:44` |
| ESTADO | Primera línea del reporte de `rapido`, `implementador` y `arquitecto`: `OK`, `ESCALAR`, `AMPLIAR` o `PENDIENTE_APROBACION`. | `~/.claude/agents/implementador.md:16` |
| OK | Valor de ESTADO: el worker terminó lo encargado. | `~/.claude/agents/implementador.md:16` |
| ESCALAR | Valor de ESTADO: la tarea excede al worker (necesita diseño). | `~/.claude/agents/implementador.md:13` |
| AMPLIAR | Valor de ESTADO: el worker necesita archivos fuera del brief. | `~/.claude/agents/implementador.md:10` |
| PENDIENTE_APROBACION | Valor de ESTADO: el worker detectó una acción sensible y no la ejecutó. | `~/.claude/orchestrator/policy.md:43` |
| VEREDICTO | Primera línea del reporte de `verificador`: `APROBADO` o `RECHAZADO`. | `~/.claude/agents/verificador.md:17` |
| Causa | Segunda línea del reporte de `verificador`: `diseño`, `implementación` o `—`. | `~/.claude/agents/verificador.md:18` |
| consolidación final | Respuesta del router al usuario al cerrar la tarea, máx. 4 líneas. | `~/.claude/orchestrator/policy.md:66` |
| config de proyecto | Archivo `.claude/orchestrator.md` de un repo. Solo puede endurecer la política. | `~/.claude/orchestrator/policy.md:69`, `~/.claude/orchestrator/project-template.md` |
| `.claude/work/` | Carpeta en la raíz git del proyecto donde los workers escriben planes y reportes largos. | `~/.claude/orchestrator/policy.md:44` |
| copia de seguridad del instalador | Directorio `<prefix>/.relevo-backups/<marca-de-tiempo>/` con lo que el instalador o el desinstalador iban a cambiar. Si su contenido coincide (checksum) con una copia anterior, se reutiliza esa; se conservan las 5 usadas más recientemente, más las fijadas (`.pinned`) y las que guardan un original de `--force`. | `scripts/relevo_install.py` (`make_backup`, `prune_backups`) |
| telemetría | Registro de métricas por worker en `~/.claude/orchestrator/log.jsonl`, escrito por el hook `orch-telemetry`. | `~/.claude/hooks/orch-telemetry` |
| `SIN_ESTADO` | Valor de `status` en telemetría cuando el reporte no contiene ESTADO, VEREDICTO ni JSON. | `~/.claude/hooks/orch-telemetry:48-52` |
| effort | Nivel de razonamiento del modelo por worker: `low`, `medium`, `high`, `xhigh`, `max`. | `~/.claude/agents/*.md:5` |
| `maxTurns` | Tope de turnos de un worker por llamada. | `~/.claude/agents/*.md:6` |
