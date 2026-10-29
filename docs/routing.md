# Routing

Este archivo cubre cómo el router decide quién ejecuta cada tarea y con qué modelo, cómo se escala y qué pasa si ninguna regla aplica. Los términos se definen en [GLOSSARY.md](GLOSSARY.md). Las rutas son absolutas desde `~/.claude/`.

Toda esta lógica es texto de la política que interpreta el modelo de la sesión principal; no hay código que la ejecute (`~/.claude/orchestrator/policy.md`).

## Paso 1: clasificar

| Condición | Quién clasifica | Fuente |
|---|---|---|
| La sesión principal es opus | El router, en línea | `~/.claude/orchestrator/policy.md:10` |
| La sesión principal no es opus | `clasificador` (haiku) | `~/.claude/orchestrator/policy.md:10` |
| JSON del `clasificador` ausente o incoherente | El router, en línea | `~/.claude/orchestrator/policy.md:10` |

El router calcula el riesgo final como el máximo entre el `clasificador`, su propio juicio, los disparadores de acción sensible, los elementos de la lista de alto riesgo y la línea `Riesgo:` del worker o del trabajo en línea. La tabla B se aplica con ese riesgo final; si la línea `Riesgo:` lo sube tras el cambio, se reaplican la tabla B y la verificación (`~/.claude/orchestrator/policy.md:11`).

### Lista de alto riesgo y línea de riesgo

| Elemento | Qué cubre | Riesgo | Fuente |
|---|---|---|---|
| 1 | Datos o efectos irreversibles: migraciones/DB, borrado o cambio de datos guardados, formato persistido, borrado masivo, pagos, envío de mensajes/posts | alto | `~/.claude/orchestrator/policy.md:57` |
| 2 | Seguridad: auth, permisos, secretos/.env/credenciales, guardas, sandbox | alto | `~/.claude/orchestrator/policy.md:58` |
| 3 | Contratos consumidos por otros: API pública, flags de CLI, formatos de config, prompts replicados, código compartido usado por comportamiento no pedido | alto | `~/.claude/orchestrator/policy.md:59` |
| 4 | Concurrencia: locks, condiciones de carrera, orden asíncrono | alto | `~/.claude/orchestrator/policy.md:60` |
| 5 | Entrega/entorno/dependencias: instaladores, release, CI, infra/deploy, git push/force, dependencias | alto | `~/.claude/orchestrator/policy.md:61` |
| 6 | Ningún test detectaría una regresión | mínimo medio | `~/.claude/orchestrator/policy.md:62` |

`implementador`, `rapido` y el trabajo en línea con cambios cierran con `Riesgo: <N>[,<N>] (<motivo>) | ninguno`. Antes de escribir `ninguno` se comprueba si el diff toca código compartido que usa un comportamiento no pedido; si es así, cuenta como elemento 3. Sin línea, el riesgo es medio como mínimo (`~/.claude/orchestrator/policy.md:63`). El `clasificador` tiene la misma lista con los mismos números (`~/.claude/agents/clasificador.md:25-31`); `tests/test_repo_consistency.py` comprueba que coinciden.

## Paso 2: tabla A (respuestas de worker y acciones sensibles)

La tabla A tiene prioridad sobre la tabla B (`~/.claude/orchestrator/policy.md:14`). La primera fila que aplique gana.

| Condición | Acción | Agente | Modelo | Fuente |
|---|---|---|---|---|
| Acción sensible a punto de ejecutarse, o un worker devuelve `PENDIENTE_APROBACION` | Parar y preguntar con AskUserQuestion: acción exacta, alcance, rollback; las opciones del worker se pasan literales, sin resumir. Sin UI interactiva: mostrar el texto completo y parar | router | sesión | `~/.claude/orchestrator/policy.md:15` |
| Worker devuelve `AMPLIAR` | Re-brief si sigue en alcance; si no, preguntar al usuario con las opciones literales | mismo worker | — | `~/.claude/orchestrator/policy.md:16` |
| `rapido` devuelve `ESCALAR` | Pasar a `implementador` | `implementador` | sonnet | `~/.claude/orchestrator/policy.md:17` |
| Resultado de `Explore` insuficiente | Seguir en línea | router | sesión | `~/.claude/orchestrator/policy.md:17` |
| Trabajo en línea que excede su fila de la tabla B | Reclasificar con la tabla B | — | — | `~/.claude/orchestrator/policy.md:17` |
| Veredicto de `verificador` en tarea de tipo `revision` | Consolidación final (no hay replan ni re-brief) | router | sesión | `~/.claude/orchestrator/policy.md:18` |
| `implementador` devuelve `ESCALAR`, o `verificador` devuelve `RECHAZADO` con `Causa: diseño` | Replan con hallazgos y plan previo si existe | `arquitecto` | opus | `~/.claude/orchestrator/policy.md:19` |
| Lo anterior y `arquitecto` ya se usó en la tarea | AskUserQuestion para otra llamada; sin permiso, parar y reportar | router | sesión | `~/.claude/orchestrator/policy.md:19` |
| `verificador` devuelve `RECHAZADO` con `Causa: implementación` o dudosa | Re-brief al mismo ejecutor (worker o en línea) con los hallazgos | mismo ejecutor | — | `~/.claude/orchestrator/policy.md:20` |
| `OK` de `Explore`, o de `rapido` sin cambios de código | Seguir en línea con su resultado | router | sesión | `~/.claude/orchestrator/policy.md:21` |
| `OK` de `arquitecto` | Un `implementador` por tramo del plan | `implementador` | sonnet | `~/.claude/orchestrator/policy.md:21` |
| Código terminado (worker o en línea) | Verificación en dos gates | ver abajo | — | `~/.claude/orchestrator/policy.md:21` |
| Verificación superada | Consolidación final | router | sesión | `~/.claude/orchestrator/policy.md:21`, `:66` |

## Paso 3: tabla B (ruta inicial por tipo)

Hay una copia en `~/.claude/agents/clasificador.md:17-23`. Las dos se generan desde `orchestrator/routing.json` del repo, que guarda las filas y los umbrales (incluido el presupuesto de evidencia de `busqueda`): `scripts/render_routing.py` reescribe el texto entre `<!-- relevo:routing:begin -->` y `<!-- relevo:routing:end -->`, y con `--check` (en `make docs-check` y en CI) falla si alguna copia diverge (`~/.claude/orchestrator/policy.md:23`). Para cambiar un umbral, edita el JSON y vuelve a generar; no edites las copias a mano.

| Tipo | Condición | Agente | Modelo | Fuente |
|---|---|---|---|---|
| `revision` | siempre | `verificador` | opus | `~/.claude/orchestrator/policy.md:27` |
| `busqueda` | ≤3 archivos conocidos y cabe en 1 lote de ≤3 llamadas (~10k tokens) | router (en línea) | sesión | `~/.claude/orchestrator/policy.md:28` |
| `busqueda` | resto, o en línea ya van >5 búsquedas secuenciales | `Explore` | haiku | `~/.claude/orchestrator/policy.md:28` |
| `mecanica` (incluye ejecutar tests/build y acciones sensibles puras como deploy o push) | ≤2 archivos y salida corta | router (en línea) | sesión | `~/.claude/orchestrator/policy.md:29` |
| `mecanica` | resto | `rapido` | haiku | `~/.claude/orchestrator/policy.md:29` |
| `arquitectura`, `bug_dificil` | siempre | `arquitecto` → plan → `implementador` por tramo (en paralelo si los archivos son disjuntos) | opus → sonnet | `~/.claude/orchestrator/policy.md:30` |
| `implementacion` (incluye escribir tests) | ≤2 archivos, complejidad ≤2, riesgo no alto | router (en línea) | sesión | `~/.claude/orchestrator/policy.md:31` |
| `implementacion` | complejidad ≥4 o >5 archivos | como `arquitectura` | opus → sonnet | `~/.claude/orchestrator/policy.md:31` |
| `implementacion` | resto | `implementador` | sonnet | `~/.claude/orchestrator/policy.md:31` |

Lo sensible no es un tipo: el `clasificador` lo marca en `necesita_aprobacion` y la tabla A (fila 1) lo para (`~/.claude/agents/clasificador.md:16`).

## Paso 4: verificación (dos gates)

| Condición | Acción | Agente | Modelo | Fuente |
|---|---|---|---|---|
| Hay código terminado | Gate determinista: test/lint/build de `.claude/orchestrator.md` o del stack | router | sesión | `~/.claude/orchestrator/policy.md:47` |
| Gate determinista en rojo | Vuelve al mismo ejecutor; cuenta como ciclo; nunca `verificador` sobre rojo | mismo ejecutor | — | `~/.claude/orchestrator/policy.md:47` |
| Gate verde y (riesgo medio o alto, o más de 1 archivo) | Verificación independiente | `verificador` | opus | `~/.claude/orchestrator/policy.md:48` |
| Gate verde, riesgo bajo y 1 archivo | Sin `verificador` | — | — | `~/.claude/orchestrator/policy.md:48` (condición inversa) |
| 2º ciclo tras `RECHAZADO` con `Causa: implementación` o dudosa | `verificador` en `modo: recheck` con `recheck_findings`: revisa solo esos; un hallazgo nuevo es advertencia y no consume ciclo | `verificador` | opus | `~/.claude/orchestrator/policy.md:36` |
| 2º ciclo tras replan | Revisión completa | `verificador` | opus | `~/.claude/orchestrator/policy.md:36` |
| Antes de la consolidación final | Comprobación del router: re-ejecuta 1 comando reportado y abre 1 cita `archivo:línea` de `Explore`. Comando distinto → gate determinista en rojo; cita distinta → `Explore` insuficiente | router | sesión | `~/.claude/orchestrator/policy.md:50` |
| La config de proyecto marca "verificador obligatorio en" esas rutas | `verificador` aunque no se cumpla lo anterior | `verificador` | opus | `~/.claude/orchestrator/project-template.md`, `~/.claude/orchestrator/policy.md:69` |

El `verificador` se lanza con contexto limpio aunque quien implementó fuera opus (`~/.claude/orchestrator/policy.md:48`). Recibe `base_commit`: solo es bloqueante un defecto causado por el cambio que no se reproduce en la base, y solo un bloqueante produce `RECHAZADO` (`~/.claude/orchestrator/policy.md:49`, `~/.claude/agents/verificador.md:13-15`). Ver [decisions/0009-riesgo-declarado-y-recheck.md](decisions/0009-riesgo-declarado-y-recheck.md). Ver [decisions/0004-verificacion-dos-gates.md](decisions/0004-verificacion-dos-gates.md).

## Escalado entre modelos

No hay escalado automático por fallo de modelo. El modelo cambia solo por estas reglas:

| De | A | Cuándo | Fuente |
|---|---|---|---|
| `rapido` (haiku) | `implementador` (sonnet) | `rapido` devuelve `ESCALAR` | `~/.claude/orchestrator/policy.md:17` |
| `implementador` (sonnet) | `arquitecto` (opus) | `ESCALAR`, o `RECHAZADO` con `Causa: diseño` | `~/.claude/orchestrator/policy.md:19` |
| `Explore` (haiku) | router (sesión) | resultado insuficiente | `~/.claude/orchestrator/policy.md:17` |
| en línea (sesión) | worker según tabla B | el trabajo excede su fila | `~/.claude/orchestrator/policy.md:17` |

Fable no está en la escalera; opus es el techo ([decisions/0002-modelo-por-rol.md](decisions/0002-modelo-por-rol.md)).

## Presupuesto

| Límite | Valor | Al agotarse | Fuente |
|---|---|---|---|
| Llamadas a `arquitecto` por tarea (incluido replan) | 1 | AskUserQuestion; sin permiso, parar y reportar | `~/.claude/orchestrator/policy.md:19`, `:35` |
| Ciclos implementar→verificar | 2 (todo RECHAZADO cuenta; el replan no reinicia; el 2º tras `Causa: implementación` es recheck y un hallazgo nuevo no consume ciclo) | Parar y reportar; advertencias abiertas a la consolidación final | `~/.claude/orchestrator/policy.md:36` |
| Turnos por llamada a worker | `maxTurns` del agente | El worker se detiene y vuelve al router con una nota de límite de turnos, sin `ESTADO` (E2E, [audit-pending.md](audit-pending.md) #2) | `~/.claude/orchestrator/policy.md:37` |
| Logbook `.claude/work/<tarea>/estado.md` | Se crea si hay `arquitecto`, más de un tramo o la tarea no se retoma solo con la petición y el diff; guarda `arquitecto: N/1` y `ciclos: N/2` | Tras compactar o reanudar, `orch-resume` lo imprime y sus contadores mandan sobre la memoria del chat; nunca bajan | `~/.claude/orchestrator/policy.md:38` |
| Paralelismo | Solo con archivos disjuntos y unidades de comportamiento independientes (~100+ líneas cada una); código, tests y docs de una unidad en el mismo worker | — | `~/.claude/orchestrator/policy.md:37` |

Una config de proyecto solo puede bajar estos valores (`~/.claude/orchestrator/policy.md:39`).

## Qué ocurre si ninguna regla aplica

La tabla B cubre los seis tipos de forma exhaustiva. Los casos sin regla explícita son:

| Caso | Comportamiento | Fuente |
|---|---|---|
| El worker devuelve un reporte sin ESTADO/VEREDICTO reconocible | No especificado; la telemetría lo registra como `SIN_ESTADO` | `~/.claude/hooks/orch-telemetry:48-52` |
| `arquitecto` no puede entregar plan | No especificado: su contrato no tiene `ESCALAR` | `~/.claude/agents/arquitecto.md:15` |
| Timeout, caída del worker o contexto excedido | No especificado | ver [failure-modes.md](failure-modes.md) |
