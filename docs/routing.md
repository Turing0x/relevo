# Routing

Este archivo cubre cómo el router decide quién ejecuta cada tarea y con qué modelo, cómo se escala y qué pasa si ninguna regla aplica. Los términos se definen en [GLOSSARY.md](GLOSSARY.md). Las rutas son absolutas desde `~/.claude/`.

Toda esta lógica es texto de la política que interpreta el modelo de la sesión principal; no hay código que la ejecute (`~/.claude/orchestrator/policy.md`).

## Paso 1: clasificar

| Condición | Quién clasifica | Fuente |
|---|---|---|
| La sesión principal es opus | El router, en línea | `~/.claude/orchestrator/policy.md:10` |
| La sesión principal no es opus | `clasificador` (haiku) | `~/.claude/orchestrator/policy.md:10` |
| JSON del `clasificador` ausente o incoherente | El router, en línea | `~/.claude/orchestrator/policy.md:10` |

El router calcula el riesgo final como el máximo entre el `clasificador`, su propio juicio y los disparadores de acción sensible. La tabla B se aplica con ese riesgo final (`~/.claude/orchestrator/policy.md:11`).

## Paso 2: tabla A (respuestas de worker y acciones sensibles)

La tabla A tiene prioridad sobre la tabla B (`~/.claude/orchestrator/policy.md:14`). La primera fila que aplique gana.

| Condición | Acción | Agente | Modelo | Fuente |
|---|---|---|---|---|
| Acción sensible a punto de ejecutarse, o un worker devuelve `PENDIENTE_APROBACION` | Parar y preguntar con AskUserQuestion: acción exacta, alcance, rollback | router | sesión | `~/.claude/orchestrator/policy.md:15` |
| Worker devuelve `AMPLIAR` | Re-brief si sigue en alcance; si no, preguntar al usuario | mismo worker | — | `~/.claude/orchestrator/policy.md:16` |
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
| Verificación superada | Consolidación final | router | sesión | `~/.claude/orchestrator/policy.md:21`, `:53` |

## Paso 3: tabla B (ruta inicial por tipo)

Hay una copia en `~/.claude/agents/clasificador.md:17-22`. Las dos deben coincidir (`~/.claude/orchestrator/policy.md:23`).

| Tipo | Condición | Agente | Modelo | Fuente |
|---|---|---|---|---|
| `revision` | siempre | `verificador` | opus | `~/.claude/orchestrator/policy.md:26` |
| `busqueda` | ≤3 archivos conocidos | router (en línea) | sesión | `~/.claude/orchestrator/policy.md:27` |
| `busqueda` | resto | `Explore` | haiku | `~/.claude/orchestrator/policy.md:27` |
| `mecanica` (incluye ejecutar tests/build y acciones sensibles puras como deploy o push) | ≤2 archivos y salida corta | router (en línea) | sesión | `~/.claude/orchestrator/policy.md:28` |
| `mecanica` | resto | `rapido` | haiku | `~/.claude/orchestrator/policy.md:28` |
| `arquitectura`, `bug_dificil` | siempre | `arquitecto` → plan → `implementador` por tramo (en paralelo si los archivos son disjuntos) | opus → sonnet | `~/.claude/orchestrator/policy.md:29` |
| `implementacion` (incluye escribir tests) | ≤2 archivos, complejidad ≤2, riesgo no alto | router (en línea) | sesión | `~/.claude/orchestrator/policy.md:30` |
| `implementacion` | complejidad ≥4 o >5 archivos | como `arquitectura` | opus → sonnet | `~/.claude/orchestrator/policy.md:30` |
| `implementacion` | resto | `implementador` | sonnet | `~/.claude/orchestrator/policy.md:30` |

Lo sensible no es un tipo: el `clasificador` lo marca en `necesita_aprobacion` y la tabla A (fila 1) lo para (`~/.claude/agents/clasificador.md:16`).

## Paso 4: verificación (dos gates)

| Condición | Acción | Agente | Modelo | Fuente |
|---|---|---|---|---|
| Hay código terminado | Gate determinista: test/lint/build de `.claude/orchestrator.md` o del stack | router | sesión | `~/.claude/orchestrator/policy.md:44` |
| Gate determinista en rojo | Vuelve al mismo ejecutor; cuenta como ciclo; nunca `verificador` sobre rojo | mismo ejecutor | — | `~/.claude/orchestrator/policy.md:44` |
| Gate verde y (riesgo medio o alto, o más de 1 archivo) | Verificación independiente | `verificador` | opus | `~/.claude/orchestrator/policy.md:45` |
| Gate verde, riesgo bajo y 1 archivo | Sin `verificador` | — | — | `~/.claude/orchestrator/policy.md:45` (condición inversa) |
| La config de proyecto marca "verificador obligatorio en" esas rutas | `verificador` aunque no se cumpla lo anterior | `verificador` | opus | `~/.claude/orchestrator/project-template.md`, `~/.claude/orchestrator/policy.md:56` |

El `verificador` se lanza con contexto limpio aunque quien implementó fuera opus (`~/.claude/orchestrator/policy.md:45`). Ver [decisions/0004-verificacion-dos-gates.md](decisions/0004-verificacion-dos-gates.md).

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
| Llamadas a `arquitecto` por tarea (incluido replan) | 1 | AskUserQuestion; sin permiso, parar y reportar | `~/.claude/orchestrator/policy.md:19`, `:33` |
| Ciclos implementar→verificar | 2 (todo RECHAZADO cuenta; el replan no reinicia) | Parar y reportar | `~/.claude/orchestrator/policy.md:34` |
| Turnos por llamada a worker | `maxTurns` del agente | El worker se detiene `[VERIFICAR: comportamiento exacto al alcanzar maxTurns; ver audit-pending.md]` | `~/.claude/orchestrator/policy.md:35` |
| Paralelismo | Solo con archivos disjuntos | — | `~/.claude/orchestrator/policy.md:35` |

Una config de proyecto solo puede bajar estos valores (`~/.claude/orchestrator/policy.md:36`).

## Qué ocurre si ninguna regla aplica

La tabla B cubre los seis tipos de forma exhaustiva. Los casos sin regla explícita son:

| Caso | Comportamiento | Fuente |
|---|---|---|
| El worker devuelve un reporte sin ESTADO/VEREDICTO reconocible | No especificado; la telemetría lo registra como `SIN_ESTADO` | `~/.claude/hooks/orch-telemetry:48-52` |
| `arquitecto` no puede entregar plan | No especificado: su contrato no tiene `ESCALAR` | `~/.claude/agents/arquitecto.md:15` |
| Timeout, caída del worker o contexto excedido | No especificado | ver [failure-modes.md](failure-modes.md) |
