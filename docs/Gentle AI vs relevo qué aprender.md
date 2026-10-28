# Gentle AI vs relevo: qué aprender

Oct 28, 2026 · @Raul

## Resumen

De gentle-ai se pueden adoptar 14 ideas sin tocar la política de relevo. Ninguna exige reescribir nada ni añadir dependencias. Las cinco que más rinden son estas: una sola fuente de verdad para la tabla B, una línea de riesgo obligatoria en cada worker, un estado de tarea en disco que se recarga tras compactar (cierra el check #6), una re-verificación limitada a los hallazgos rechazados y un `/orch-doctor` de diagnóstico.

gentle-ai es un instalador en Go (MIT, v4.0.0, 7,2k estrellas, más de 3.700 commits; último commit el 28-10-2026) que configura agentes ya instalados, Claude Code entre ellos. Su flujo ODD coincide en lo esencial con relevo: trabajar en línea por defecto y delegar solo cuando hay un motivo declarado. Las diferencias de fondo son tres. Asigna los modelos de forma estática por fase, con sonnet por defecto en todo. Pone `bypassPermissions` y se protege con una lista `deny`. Y valida el trabajo con un binario determinista en lugar de con el prompt.

La lección principal no es una función concreta, es un patrón. Todo lo que el modelo hace mal o de forma poco fiable lo han sacado del prompt y lo han pasado a código, con umbrales numéricos explícitos. relevo ya aplica ese patrón a la seguridad. Lo que queda es extenderlo al estado de las tareas y al routing.

## Lo que no se toca

Toda idea que choque con alguno de estos puntos se descarta o se adapta. La lista sale de `orchestrator/policy.md` y de los ADR de `docs/decisions/`.

1. **Modelo por rol y routing dinámico por tarea** (ADR 0002). El router clasifica cada petición y elige entre haiku, sonnet y opus. El modelo no se fija por fase.
2. **Refuerzo duro** (ADR 0001, 0008). Las reglas críticas se aplican con `permissions.ask`/`deny` y con hooks. Nada de `bypassPermissions`.
3. **Delegar solo por motivo** (ADR 0003): aislamiento de contexto, revisión independiente o paralelismo real.
4. **Dos gates** (ADR 0004). Primero el determinista y después el `verificador` opus con contexto limpio, si el riesgo es medio o superior o si cambia más de un archivo.
5. **Presupuesto** (ADR 0007): como máximo 1 llamada a `arquitecto` y 2 ciclos de implementar y verificar por tarea.
6. **Acciones sensibles** (§6): siempre con aprobación humana, indicando la acción exacta, su alcance y el rollback.
7. **Contrato de salida corto** (ADR 0005): `ESTADO`/`VEREDICTO` en 8 líneas como máximo, y el detalle en `.claude/work/`.
8. **El proyecto solo endurece** (§8). Cualquier configuración de proyecto que relaje la política se ignora.
9. **Implementación mínima**: archivos de texto, Python de la biblioteca estándar y un instalador con manifest reversible. Sin binarios ni servicios externos obligatorios.
10. **Telemetría local** (ADR 0006). Nada sale de la máquina.

## Cómo funciona gentle-ai en Claude Code

En Claude Code, gentle-ai instala un prompt de orquestador, ocho subagentes de revisión, cuatro hooks y una capa de permisos. El routing es un texto que se genera desde constantes en Go.

### Routing: ODD

- **Dos rutas.** *Direct inline* para tareas pequeñas y *delegated direct* cuando se cumple un disparador. Su lema es que el número de archivos nunca decide el tamaño.
- **Tarea pequeña.** Tiene que cumplir tres condiciones. La primera, que esté entendida, y que eso pueda demostrarse con un lote de lectura de 3 llamadas y unos 10k tokens como máximo. La segunda, que no toque ningún elemento de alto riesgo. La tercera, que pase el **test de reanudación**: si la sesión se cortara ahora, alguien podría terminarla solo con la petición y el `git diff`.
- **Explorador.** Se usa cuando entender el problema exige más de unas 5 búsquedas secuenciales. Devuelve unos 2k tokens como máximo con evidencia `path:line`, y el padre comprueba una de las citas.
- **Escritor delegado.** Solo con un motivo con nombre: unidades independientes con superficies disjuntas (cada una de más o menos 100 líneas o varios minutos de trabajo, porque un subagente gasta 1-2 minutos en leer antes de escribir) o el límite de contexto de unos 150k. Un mismo comportamiento nunca se reparte entre escritores de código, tests y documentación.
- **Verificador independiente.** Solo cuando el cambio toca un elemento con nombre de la lista de alto riesgo.
- **Superficie de edición.** El padre pasa `## Allowed edit surfaces` con rutas exactas o globs estrechos, nunca `.`. Si no puede derivarla, presenta una lista de rutas candidatas para aprobar o rechazar.

### Lista de alto riesgo (6 elementos)

1. Datos o efectos irreversibles: migraciones, borrado o cambio de datos guardados, cambios de formato persistido.
2. Seguridad: autenticación, permisos, credenciales, guardas, sandbox.
3. Contratos que otros consumen: API pública, flags de CLI, formatos de configuración, prompts replicados.
4. Concurrencia: locks, condiciones de carrera, orden asíncrono.
5. Entrega o entorno: instaladores, release, CI, deploy, dependencias.
6. Ningún test detectaría una regresión.

Cada cambio termina con una **línea de riesgo**: `Risk: item N (reason)` o `Risk: none`. Antes de escribir `none`, el agente tiene que comprobar si el diff toca código compartido que usa otro comportamiento que no se pidió. Si es así, cuenta como elemento 3.

### Verificación y correcciones

- **Niveles.** *Passive* (documentación): solo relectura estructural. *Medium*: el escritor se autoverifica con los comandos de `## Verification` e informa `<comando>: <resultado observado>`. *High*: añade un verificador independiente.
- **Comprobación del padre.** En todos los niveles, el padre vuelve a ejecutar uno de los comandos que reportó el worker antes de entregar.
- **Límite de correcciones.** Hay un lote de corrección que arregla todos los bloqueantes, seguido de una re-verificación **limitada a esos bloqueantes**, sin barrido completo. Una segunda corrección solo se permite si persiste el mismo bloqueante. Un hallazgo nuevo nunca da derecho a otro ciclo. Lo que quede abierto pasa a *Needs your decision*.
- **Qué se le pasa al verificador.** El documento completo de la tarea, el commit base y los comandos de prueba. Ejecuta las pruebas en una copia temporal (`mktemp -d`) y no deja archivos en el workspace. Solo cuenta como bloqueante un defecto causado por el cambio que no se reproducía en la base. El escritor commitea esas pruebas como tests de regresión.

### Revisión RDD (opcional, activada por defecto)

El binario congela el candidato (hash del diff), calcula el riesgo y elige entre 0, 1 o 4 lentes: `review-risk`, `review-resilience`, `review-readability` y `review-reliability`. Todas tienen `tools: []` y un *precision gate*: solo se informa de un hallazgo que se pueda defender con evidencia, y los de estilo están prohibidos. Después, un `review-refuter` intenta refutar cada bloqueante inferencial y lo marca como `corroborated`, `refuted` o `inconclusive`. El veredicto lo decide el binario, no el modelo.

### Modelos, permisos y hooks

- **Modelos.** Se asignan desde la TUI por fase: `fable`, `opus`, `sonnet` o `haiku`, con effort configurable. Por defecto, `odd-explorer`, `odd-worker` y `odd-verify` usan sonnet.
- **Permisos.** `"defaultMode": "bypassPermissions"` más 24 reglas `deny`: `.env`, `.ssh`, `*.pem`, `*.key`, `.aws/credentials`, `rm -rf /` y similares. No hay ninguna regla `ask`.
- **Hooks.** `SessionStart` (matcher `startup|resume|clear|compact`) y `Stop` llevan el registro de skills y el aviso de revisión. `SubagentStop` y `Stop` envían telemetría. No hay `PreToolUse` de bloqueo. Los hooks se escriben en un `settings.json` que acepta JSONC sin tocar el resto de bytes, y si hay ambigüedad se niegan a escribir.

### Herramientas alrededor

- **`gentle-ai doctor`**: diagnóstico de solo lectura. Cada comprobación devuelve `pass`, `warn` o `fail` con un remedio identificado. Comprueba los binarios en el PATH (y si alguno queda tapado por otro), el estado, la versión de los assets, Engram y el espacio en disco.
- **`sync --dry-run`** y **backups**: `tar.gz` deduplicado por checksum, se conservan los 5 últimos y se pueden fijar.
- **Engram**: memoria en SQLite con interfaz MCP. Los workers terminan con un bloque `## Key Learnings` de 1 a 5 puntos que se captura de forma pasiva.
- **Skill registry**: `.atl/skill-registry.md`. El padre pasa a cada subagente las rutas exactas de `SKILL.md` en lugar de dejar que las descubra.
- **E2E deterministas**: un agente real contra un servidor HTTP local que hace de modelo y devuelve respuestas guionizadas. Sin API keys y sin coste.

## Comparativa

relevo gana en el control del coste y en cómo aplica las reglas. gentle-ai gana en estado persistente, en precisión de los umbrales y en herramientas a su alrededor.

| Aspecto | relevo | gentle-ai | Ventaja |
| --- | --- | --- | --- |
| Elección de modelo | Dinámica por tarea (tabla B + `clasificador`) | Estática por fase, sonnet por defecto | relevo |
| Criterio para delegar | Motivo (ADR 0003) + número de archivos y complejidad | Motivo + presupuesto de evidencia numérico; el número de archivos nunca decide | gentle-ai en precisión |
| Permisos | 44 `ask` + 2 `deny` | `bypassPermissions` + 24 `deny` | relevo |
| Hooks de bloqueo | `block-force-push`, `guard-secrets` (`PreToolUse`) | Ninguno | relevo |
| Riesgo | Clasificador + palabras clave, 3 niveles | Lista numerada de 6 elementos + línea de riesgo obligatoria en cada cambio | gentle-ai |
| Cuándo hay verificador | Riesgo medio o más, o más de 1 archivo | Solo alto riesgo con nombre | relevo en seguridad, gentle-ai en coste |
| Re-verificación | Ciclo completo (máx. 2) | Limitada a los bloqueantes; un hallazgo nuevo no da ciclo | gentle-ai |
| Severidad | Libre, máx. 8 hallazgos | Bloqueante = causado por el cambio y ausente en la base | gentle-ai |
| Estado de tarea | Solo en el contexto del router (check #6 pendiente) | Logbook en disco + Engram + hook en `SessionStart:compact` | gentle-ai |
| Superficie de edición | "Archivos permitidos" en el brief | Sección con formato estricto, nunca `.`, candidatos para aprobar | gentle-ai |
| Fuente del routing | Dos copias de la tabla B sincronizadas a mano | Constantes en Go que se renderizan al prompt | gentle-ai |
| Diagnóstico | No hay | `doctor` con pass/warn/fail + remedio | gentle-ai |
| Backups | `.relevo-backups/<timestamp>` sin retención | Dedup por checksum, se guardan 5, se pueden fijar | gentle-ai |
| Tests de agente | Unitarios de hooks e instalador | E2E con modelo falso guionizado | gentle-ai |
| Telemetría | Local, por agente (`/orch-stats`) | Remota y anónima | relevo |
| Alcance | Solo Claude Code, unas 370 líneas de prompts y hooks | Unos 15 agentes, Go, TUI | Según el objetivo |

## Qué adoptar

Son 14 ideas. Todas añaden reglas o herramientas y ninguna relaja la política. Esfuerzo: S son menos de 2 horas, M es un día y L, varios días.

| # | Idea | Cómo en relevo | Archivos | Esfuerzo |
| --- | --- | --- | --- | --- |
| 1 | Fuente única de la tabla B | `orchestrator/routing.json` + `scripts/render_routing.py`, que reescribe las dos copias entre marcadores. `test_repo_consistency.py` falla si no coinciden | `policy.md`, `clasificador.md`, `scripts/`, `tests/` | S |
| 2 | Línea de riesgo obligatoria | Lista numerada de 6 elementos de alto riesgo en §6 bis. `implementador`, `rapido` y el trabajo en línea cierran con `Riesgo: N (motivo)` o `Riesgo: ninguno`. Entra en el `max()` de §1 | `policy.md`, `clasificador.md`, `implementador.md`, `rapido.md`, schemas | S |
| 3 | Presupuesto de evidencia en línea | Se añade a la fila `busqueda`: en línea si cabe en 1 lote de 3 llamadas como máximo (unos 10k tokens). Más de 5 búsquedas secuenciales llevan a `Explore`. Complementa el número de archivos, no lo sustituye | `policy.md` §2B, `routing.md` | S |
| 4 | Comprobación del router | Antes de §7, el router vuelve a ejecutar 1 comando que reportó el worker y abre 1 cita `archivo:línea` de `Explore` | `policy.md` §5 y §7 | S |
| 5 | Re-verificación limitada | Tras un RECHAZADO, el `verificador` recibe `modo: recheck` y la lista de hallazgos, y comprueba solo esos. Un hallazgo nuevo pasa a ser advertencia y no gasta ciclo | `verificador.md`, `policy.md` §3 | S |
| 6 | Severidad con base | Se le pasa el commit base al `verificador`. Bloqueante es un defecto causado por el cambio que no se reproduce en la base. Ignorar en silencio una opción explícita o cambiar una salida que nadie pidió cambiar es siempre bloqueante | `verificador.md`, `brief.schema.json` | S |
| 7 | *Precision gate* | En el `verificador`: solo hallazgos que se puedan defender con evidencia, y nada de estilo salvo que oculte un defecto. Si está limpio, `Hallazgos: ninguno` | `verificador.md` | S |
| 8 | Superficie de edición estricta | Sección `## Superficie permitida` en el brief: rutas o globs estrechos, nunca `.` ni rutas absolutas. Si el router no puede derivarla, presenta los candidatos con AskUserQuestion | `policy.md` §4, `brief.schema.json` | S |
| 9 | Unidades de escritura | En §3, se paraleliza solo con unidades de comportamiento independientes de al menos unas 100 líneas cada una. Código, tests y documentación de una misma unidad van juntos | `policy.md` §3 | S |
| 10 | Prompts bloqueantes sin pérdida | Al pasar al usuario un PENDIENTE\_APROBACION o un AMPLIAR, se mantienen todas las opciones sin resumir. Si no hay interfaz interactiva, se muestra el texto completo y se para | `policy.md` §2A | S |
| 11 | Estado de tarea + hook de reanudación | Logbook `.claude/work/<tarea>/estado.md` con contadores, tramos y siguiente paso. Un hook `orch-resume` en `SessionStart` (matchers `compact` y `resume`) lo reinyecta. Resuelve el check #6 | `policy.md` §3, `hooks/`, settings template | M |
| 12 | `/orch-doctor` | `orchestrator/doctor.py` de solo lectura: frontmatter válido, hooks ejecutables y registrados, `env`, drift del manifest, Python 3.9 o superior, el import en `CLAUDE.md` y `.claude/work/` en `.gitignore`. Salida pass/warn/fail + remedio | `orchestrator/`, `commands/`, instalador | M |
| 13 | Backups con retención y escritura que respeta JSONC | Dedup por checksum, se guardan 5 y se pueden fijar. El merge de `settings.json` falla sin escribir si encuentra comentarios o claves duplicadas | `relevo_install.py`, `test_install.py` | S |
| 14 | E2E con modelo falso | Servidor HTTP local que imita la API de Messages, apuntado con `ANTHROPIC_BASE_URL`. Guiones que intentan un force push, leer `.env` o terminar un worker. Se verifican los hooks y `log.jsonl` | `tests/e2e/`, CI | L |

### Detalle de las cinco prioritarias

**1. Fuente única de la tabla B.** Hoy `failure-modes.md` dice "no detectado" para la desincronización. gentle-ai lo resuelve generando el prompt desde datos (`internal/components/agentguidance/routing.go`). En relevo basta un JSON con las filas, umbrales incluidos, y un script que reescriba el texto entre marcadores `<!-- relevo:routing:begin -->` y `<!-- relevo:routing:end -->` en los dos archivos. CI ejecuta el script en modo `--check`. Los números del punto 3 también van en ese JSON.

**2. Línea de riesgo.** Hoy el riesgo se decide antes de actuar. La línea añade una comprobación después, sobre el diff real. Si el worker declara un elemento que el clasificador no vio, el riesgo final sube y §5 lanza el `verificador`, que es justo el refuerzo que pide el `max()` de §1. Los 6 elementos de gentle-ai encajan casi uno a uno con la lista de palabras clave de `clasificador.md`, así que lo que hay que hacer es numerarla y unificarla. El sexto elemento (ningún test detectaría la regresión) es nuevo y muy útil.

**5 y 6. Re-verificación limitada y severidad con base.** Juntas reducen el gasto en opus sin quitar ninguna revisión. El límite de 2 ciclos sigue igual. Lo que cambia es que el segundo ciclo es más barato y no puede abrir frentes nuevos. Hacen falta dos campos nuevos en `brief.schema.json`: `base_commit` y `recheck_findings[]`.

**11. Estado de tarea en disco.** Es la mejora con más impacto, porque los contadores de presupuesto son hoy una regla que se puede perder al compactar. Propuesta:

- El router crea `estado.md` cuando la tarea no pasa el test de reanudación, o cuando hay `arquitecto` o más de un tramo.
- Campos: petición literal, ruta, `arquitecto: 0/1`, `ciclos: N/2`, tramos con su estado, último veredicto y siguiente paso.
- El hook `orch-resume` (Python stdlib, síncrono, timeout de 5 s) imprime el `estado.md` activo en `SessionStart:compact` y `resume`. Claude Code añade la salida de ese hook al contexto **\[VERIFICAR en sesión real\]**.
- Engram queda como integración opcional documentada, nunca como dependencia.

**12. `/orch-doctor`.** Convierte buena parte de `audit-pending.md` y de `failure-modes.md` en comprobaciones repetibles. Usa el mismo formato que gentle-ai: un id estable por comprobación (`hooks:registered`, `manifest:drift`, `routing:sync`…), un estado y un remedio, que nunca se ejecuta solo.

## Qué no adoptar

Estas piezas funcionan en gentle-ai, pero romperían alguno de los principios de relevo o le cargarían un peso que no compensa.

| Pieza de gentle-ai | Por qué no | Choca con |
| --- | --- | --- |
| `bypassPermissions` con solo `deny` | Una lista negra nunca está completa. relevo pide confirmación para lo sensible | Principio 2 |
| Verificador solo en alto riesgo con nombre | Ahorra opus, pero se queda sin revisar el riesgo medio. Las ideas 5 y 6 reducen el coste sin quitar la revisión | Principio 4 |
| "El número de archivos nunca decide" como única regla | La tabla B es la base del routing por coste. El presupuesto de evidencia se añade, no la sustituye | Principio 1 |
| Modelo fijo por fase | Es justo lo que relevo hace mejor | Principio 1 |
| Maquinaria RDD (hash del candidato, recibos, handles AES, lentes 4R + refutador) | Necesita un binario y añade varias llamadas a opus por revisión. Se aprovecha la idea (veredicto desde la evidencia, *precision gate*), no la implementación | Principios 5 y 9 |
| Engram como requisito | Servicio externo. Mejor integración opcional | Principio 9 |
| Commits automáticos por unidad de unas 400 líneas | En relevo, el control de git lo tiene el usuario | Principio 6 |
| Telemetría remota | relevo promete que nada sale de la máquina | Principio 10 |
| `## Key Learnings` en cada worker | Alarga el contrato de salida. Se puede revisar cuando haya memoria persistente | Principio 7 |
| Reporte automático de defectos a GitHub | Es una acción externa que hoy necesita aprobación en §6. Demasiada ceremonia para relevo | Principio 6 |
| Personas, output styles, TUI, soporte multiagente | Fuera del alcance: relevo es solo para Claude Code | — |

Una idea queda en el aire. Las lentes 4R podrían entrar como **foco** dentro del brief del `verificador` (riesgo, resiliencia, legibilidad, fiabilidad), elegido por el router según los elementos de riesgo declarados. Sería una sola llamada con más dirección, no cuatro. Merece una prueba después de la fase 1.

## Plan por fases

Son tres fases, cada una con su release 0.x. Según CONTRIBUTING, los cambios en prompts, agentes, hooks e instalador necesitan revisión extra, así que conviene un PR por fase.

1. **Fase 1 — Prompts (0.2.0).** Ideas 2, 3, 4, 5, 6, 7, 8, 9 y 10. Solo cambian `policy.md`, los agentes y los schemas. Se añade un ADR 0009 ("riesgo declarado y re-verificación limitada") y se actualizan `routing.md` y `failure-modes.md`.
2. **Fase 2 — Estructura (0.3.0).** Ideas 1, 11 y 13. Generador de la tabla B, logbook con el hook `orch-resume` y backups con retención. Se cierran los checks #6 de `audit-pending.md` y la fila "copias desincronizadas" de `failure-modes.md`.
3. **Fase 3 — Herramientas (0.4.0).** Ideas 12 y 14. `/orch-doctor` y el E2E con modelo falso. Este último puede automatizar varios checks de `audit-pending.md` (#2, #4, #5) **\[VERIFICAR que Claude Code acepta `ANTHROPIC_BASE_URL` hacia un servidor local con hooks reales\]**.

Después de cada fase, conviene comparar `/orch-stats` en 30 días: llamadas a opus por tarea, `tope` y `SIN_ESTADO`.

### Prompt para Claude Code (fase 1)

```
Repo: relevo. Implementa la fase 1 del documento "Gentle AI vs relevo: qué aprender" (ideas 2-10). No relajes ninguna regla de orchestrator/policy.md; solo añade.

1. policy.md: añade §6bis con la lista numerada de alto riesgo (1 datos/irreversible, 2 seguridad, 3 contratos consumidos por otros, 4 concurrencia, 5 entrega/entorno/dependencias, 6 sin test que detecte regresión). En §1, riesgo final = max(clasificador, juicio, §6, línea de riesgo del worker).
2. implementador.md y rapido.md: nueva línea obligatoria en la salida `Riesgo: <N> (<motivo>) | ninguno`; antes de "ninguno", comprobar si el diff toca código compartido usado por comportamiento no pedido (= 3). Mantén ≤8 líneas.
3. clasificador.md: unifica su lista de palabras clave con §6bis (mismos números).
4. §2B fila busqueda: en línea si cabe en 1 lote ≤3 llamadas (~10k tokens); >5 búsquedas secuenciales → Explore. Sincroniza la copia en clasificador.md.
5. §5/§7: el router re-ejecuta 1 comando reportado y comprueba 1 cita archivo:línea de Explore antes de consolidar.
6. verificador.md: recibe base_commit; bloqueante = causado por el cambio y no reproducible en base; precision gate (solo hallazgos defendibles, sin estilo); modo recheck que revisa solo los hallazgos previos y marca los nuevos como advertencia.
7. §3: tras RECHAZADO, el segundo ciclo es recheck; un hallazgo nuevo no consume ciclo. Paralelizar solo unidades de comportamiento independientes (~100+ líneas cada una; código+tests+docs juntos).
8. §4 y brief.schema.json: sección "Superficie permitida" (rutas/globs, nunca "." ni absolutas); añade base_commit y recheck_findings[]. Si no se puede derivar, AskUserQuestion con candidatos.
9. §2A1: al relayar PENDIENTE_APROBACION/AMPLIAR, conservar todas las opciones literales; sin UI interactiva, mostrar completo y parar.
10. Actualiza schemas de salida, docs/routing.md, docs/failure-modes.md, docs/agents/*.md y añade docs/decisions/0009-riesgo-declarado-y-recheck.md.

Tests: tests/test_repo_consistency.py y check_schemas.py deben pasar; añade casos para la línea Riesgo en los schemas. No hagas commit ni push sin pedirme confirmación.
```

## Fuentes

Se revisó el commit de `main` del 28-10-2026: `test(opencode): pin that no agent permission shadows sensitive-path denies (#5817)`.

- [Gentle Stack](https://gentlemanprogramming.com/#top)
- [gentle-ai (repositorio)](https://github.com/Gentleman-Programming/gentle-ai)
- [Orquestador de Claude Code](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/assets/claude/orchestrator.md)
- [Secciones compartidas de ODD](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/assets/skills/_shared/odd-orchestrator-sections.md)
- [Task Size y lista de alto riesgo (`routing.go`)](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/components/agentguidance/routing.go)
- [Permisos de Claude Code (`inject.go`)](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/components/permissions/inject.go)
- [Hooks de Claude Code (`claude.go`)](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/components/agenthooks/claude.go)
- [Asignación de modelos (`claude_model_picker.go`)](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/tui/screens/claude_model_picker.go)
- [Agentes de revisión (`review-risk.md`, `review-refuter.md`)](https://github.com/Gentleman-Programming/gentle-ai/tree/main/internal/assets/claude/agents)
- [Trigger rules](https://github.com/Gentleman-Programming/gentle-ai/blob/main/docs/trigger-rules.md)
- [Review integration (RDD)](https://github.com/Gentleman-Programming/gentle-ai/blob/main/docs/review-integration.md)
- [Testing agents deterministically](https://github.com/Gentleman-Programming/gentle-ai/blob/main/docs/testing-agents-deterministically.md)
- [Doctor (`doctor.go`)](https://github.com/Gentleman-Programming/gentle-ai/blob/main/internal/doctor/doctor.go)
- [Backup y rollback](https://github.com/Gentleman-Programming/gentle-ai/blob/main/docs/rollback.md)
- [Engram](https://github.com/Gentleman-Programming/gentle-ai/blob/main/docs/engram.md)

De relevo: `orchestrator/policy.md`, `agents/*.md`, `docs/audit-pending.md` y `docs/failure-modes.md` de la copia local.
