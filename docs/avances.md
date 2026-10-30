# Avances: de 0.1.0 a 0.2.0 y siguientes

Registro de lo hecho tras la primera release. Recoge qué se cambió, por qué, cómo se verificó y qué queda pendiente. Las rutas son relativas a la raíz del repo; las de la instalación, absolutas desde `~/.claude/`. Última actualización: 2026-10-30.

## Resumen

- Se adoptaron las 14 ideas de [Gentle AI vs relevo: qué aprender](Gentle%20AI%20vs%20relevo%20qu%C3%A9%20aprender.md). Ninguna relaja la política; todas añaden reglas o herramientas.
- El plan preveía tres releases (0.2.0, 0.3.0 y 0.4.0). Al final las tres fases salieron juntas en **0.2.0**.
- Después de la release se llevaron al repo dos cambios que solo existían en la instalación global: el §9 "Relevo de sesión" y el modo multi-repo de `/orchestrator-init`. Están en `[Unreleased]` del [CHANGELOG](../CHANGELOG.md).
- La instalación de `~/.claude` se reinstaló desde el repo. Ahora la gestiona el instalador y `/orch-doctor` da 9 pass, 0 warn, 0 fail.
- 2026-10-30: `/orch-stats` mostraba la mitad de las llamadas como `SIN_ESTADO` y al `arquitecto` siempre en el tope de turnos. La causa era una carrera en `orch-telemetry`, no los agentes. Se corrigió el hook, se subieron `maxTurns` (`arquitecto` 45, `verificador` 35) y se reclasificó el log histórico (PR #15).

## Cronología

| Fecha | PR | Commit en `main` | Contenido |
|---|---|---|---|
| 2026-10-22 | — | `d1f0ace` | Release 0.1.0 (alpha) |
| 2026-10-22 | [#1](https://github.com/Turing0x/relevo/pull/1), [#2](https://github.com/Turing0x/relevo/pull/2) | `c38078b`, `37a2984` | Actualizaciones de Dependabot |
| 2026-10-28 | [#7](https://github.com/Turing0x/relevo/pull/7) | `0d7e60b` | Fase 1: prompts (ideas 2-10) |
| 2026-10-28 | [#8](https://github.com/Turing0x/relevo/pull/8) | `c675946` | Fase 2: estructura (ideas 1, 11 y 13) |
| 2026-10-29 | [#11](https://github.com/Turing0x/relevo/pull/11) | `5be9faf` | Fase 3: herramientas (ideas 12 y 14) |
| 2026-10-29 | [#12](https://github.com/Turing0x/relevo/pull/12) | `68471a0` | Release 0.2.0, tag `v0.2.0` y [release en GitHub](https://github.com/Turing0x/relevo/releases/tag/v0.2.0) |
| 2026-10-29 | [#13](https://github.com/Turing0x/relevo/pull/13) | `c8cdc7e` | §9 "Relevo de sesión" y `/orchestrator-init` multi-repo |
| 2026-10-29 | [#14](https://github.com/Turing0x/relevo/pull/14) | `8bac2be` | Este registro de avances |
| 2026-10-30 | [#15](https://github.com/Turing0x/relevo/pull/15) | `0aeaa5d` | `orch-telemetry`: reintento de lectura del transcript; `maxTurns` 45/35 |

Todos los PR se mergearon con squash. El ruleset de `main` pide la aprobación de un code owner y el autor no puede aprobar su propio PR, así que se usó `--admin` (bypass permitido solo vía PR) con el CI en verde.

## Fase 1: prompts (PR #7)

Objetivo: que el riesgo se compruebe también después del cambio, que la segunda revisión sea más barata sin quitarla y que los briefs acoten mejor qué se puede tocar.

| Idea | Qué se hizo | Dónde |
|---|---|---|
| 2. Línea de riesgo | Lista de alto riesgo numerada (§6bis), con la misma numeración en `clasificador`. Elementos 1-5 → riesgo alto; 6 ("ningún test detectaría una regresión") → mínimo medio. `implementador`, `rapido` y el trabajo en línea con cambios cierran con `Riesgo: <N>[,<N>] (<motivo>) \| ninguno`. Si falta la línea, riesgo mínimo medio. El riesgo final es el máximo de todo y, si sube tras el cambio, se reaplican la tabla B y §5 | `orchestrator/policy.md` §1 y §6bis, `agents/clasificador.md`, `agents/implementador.md`, `agents/rapido.md`, schemas de salida |
| 3. Presupuesto de evidencia | `busqueda` va en línea solo si son ≤3 archivos conocidos y cabe en 1 lote de ≤3 llamadas (~10k tokens). Más de 5 búsquedas secuenciales → `Explore` | `policy.md` §2B, `routing.md` |
| 4. Comprobación del router | §5.3: antes de §7, el router vuelve a ejecutar 1 comando reportado por un worker y abre 1 cita de `Explore`. Si no coincide, cuenta como gate en rojo o como `Explore` insuficiente | `policy.md` §5 y §7 |
| 5. Re-verificación limitada | Tras un RECHAZADO por implementación, el 2º ciclo va en `modo: recheck` con `recheck_findings`. Un hallazgo nuevo es advertencia y no gasta ciclo. Tras un replan, la revisión es completa | `policy.md` §3, `agents/verificador.md` |
| 6. Severidad con base | El `verificador` recibe `base_commit`. Bloqueante = causado por el cambio y no reproducible en la base (se comprueba en una copia temporal con `git archive`). Siempre bloqueantes: criterio incumplido, regresión de un fix anterior, opción explícita ignorada, salida no pedida cambiada, secretos y acción sensible sin aprobar | `agents/verificador.md`, `docs/contracts/brief.schema.json` |
| 7. Precision gate | Solo hallazgos defendibles con evidencia; nada de estilo salvo que oculte un defecto; `Hallazgos: ninguno` si está limpio | `agents/verificador.md` |
| 8. Superficie permitida | El brief lleva `## Superficie permitida` con rutas o globs estrechos (nunca `.` ni rutas absolutas). Si no se puede derivar, AskUserQuestion con candidatos | `policy.md` §4, `brief.schema.json` |
| 9. Unidades de escritura | Workers en paralelo solo para unidades de comportamiento independientes (~100+ líneas cada una), con código, tests y docs juntos | `policy.md` §3 |
| 10. Prompts bloqueantes sin pérdida | `PENDIENTE_APROBACION` y `AMPLIAR` se pasan al usuario con todas las opciones literales; sin interfaz interactiva, texto completo y parar | `policy.md` §2A |

Documentación: [ADR 0009](decisions/0009-riesgo-declarado-y-recheck.md), `routing.md`, `failure-modes.md`, `GLOSSARY.md`, `ARCHITECTURE.md`, fichas de `docs/agents/`, ejemplos y citas `policy.md:N` reajustadas.

Tests añadidos: `RiskLineTests`, `PolicySyncTests` (§6bis frente a la lista del `clasificador` y la fila `busqueda`) y `BriefAndVerifierContractTests` en `tests/test_repo_consistency.py`, más validación con `jsonschema` cuando está disponible.

Revisión: el primer `verificador` dio RECHAZADO (la regla "lo que ya fallaba en base es advertencia" dejaba pasar un criterio incumplido, y una cita estaba mal). Se corrigió y el recheck dio APROBADO.

## Fase 2: estructura (PR #8)

| Idea | Qué se hizo | Dónde |
|---|---|---|
| 1. Fuente única de la tabla B | `orchestrator/routing.json` contiene filas y umbrales. `scripts/render_routing.py` reescribe las dos copias (§2B y `clasificador`) entre marcadores `relevo:routing`. `--check` corre en `make docs-check` y en CI | `orchestrator/routing.json`, `scripts/render_routing.py` |
| 11. Logbook + reanudación | `.claude/work/<tarea>/estado.md` con petición literal, ruta, `arquitecto: N/1`, `ciclos: N/2`, tramos, último veredicto y siguiente paso. Tras compactar o reanudar, sus contadores mandan y nunca bajan. El hook `orch-resume` (SessionStart, matchers `compact` y `resume`, 5 s) lo imprime; se niega si `.claude/work/` no está en `.gitignore` y recorre el directorio con descriptores (`O_NOFOLLOW`) | `policy.md` §3, `hooks/orch-resume`, `templates/settings.example.json` |
| 13. Backups y JSONC | Backups deduplicados por checksum; se guardan los 5 más recientes, los fijados y los que tienen un original reemplazado con `--force`. `--pin-backup` y comando `backups` (`--pin`, `--unpin`). El merge de `settings.json` falla sin escribir si hay comentarios o claves duplicadas | `scripts/relevo_install.py` |

Documentación: [ADR 0010](decisions/0010-fuente-unica-logbook-y-backups.md). Se cerró el check #6 de [audit-pending.md](audit-pending.md) y la fila "copias desincronizadas" de `failure-modes.md`.

Tests: `tests/test_orch_resume.py` y ampliaciones de `tests/test_install.py` y `tests/test_repo_consistency.py`.

## Fase 3: herramientas (PR #11)

| Idea | Qué se hizo | Dónde |
|---|---|---|
| 12. `/orch-doctor` | Diagnóstico de solo lectura con 9 checks: `python:version`, `frontmatter:valid`, `hooks:executable`, `hooks:registered`, `env`, `manifest:drift`, `claude-md:import`, `gitignore:work` y `routing:sync`. Cada uno tiene id estable, estado `pass`/`warn`/`fail` y un remedio que nunca se aplica solo. Sale con código 1 si algo falla. El instalador copia `doctor.py`, `routing.json` y `render_routing.py` | `orchestrator/doctor.py`, `commands/orch-doctor.md` |
| 14. E2E con modelo falso | El CLI real de Claude Code contra un servidor local que imita la API de Messages (`ANTHROPIC_BASE_URL`), con respuestas guionizadas. Cubre force push, lectura de `.env`, reportes y telemetría, `maxTurns`, errores de API de un worker, límite de profundidad, override de `Explore` y `orch-resume` en `compact` y `resume`. Opcional con `make e2e`; fuera de `make check` y de CI; sin API key ni coste | `tests/e2e/` |

Documentación: [ADR 0011](decisions/0011-doctor-y-e2e.md). En [audit-pending.md](audit-pending.md) quedaron cerrados los checks #1, #2, #3, #4 y #8, y el #5 en parte.

Hallazgos de comportamiento con Claude Code 2.1.312:
- Un worker que se detiene por `maxTurns` o por un error de API no dispara `SubagentStop`, así que no deja línea en `log.jsonl`.
- En `claude -p`, el hook asíncrono `orch-telemetry` no llega a ejecutarse.
- Por eso `ARCHITECTURE.md` ya no dice que se registran todos los workers, y `/orch-stats` avisa de que `tope` se queda corto.

## Release 0.2.0 (PR #12)

- `VERSION = "0.2.0"` en `scripts/relevo_install.py`, sección `[0.2.0] - 2026-10-29` en el CHANGELOG con enlaces de comparación, y versión `0.2.0` en `README.md` y `README.es.md`.
- Tag anotado `v0.2.0` sobre `68471a0` y release en GitHub con las notas del CHANGELOG.

## Después de 0.2.0: §9 y `/orchestrator-init` multi-repo (PR #13)

La instalación global se había hecho a mano antes de existir el instalador y tenía dos cambios propios que no estaban en el repo. Reinstalar los habría borrado, así que primero se llevaron al repo:

- **§9 "Relevo de sesión"** (`orchestrator/policy.md:72-73`): en sesiones largas, tras compactar o antes de cerrar con trabajo a medias, el router sobrescribe `HANDOFF.md` (en `.claude/work/` si hay repo git; si no, en la raíz) con lo hecho, lo pendiente, archivos clave, decisiones, preguntas abiertas y el presupuesto §3 (con los contadores del logbook si existe). Una sesión nueva lo lee antes de actuar. La línea 2 de la política dice a los workers que ignoren §9. Va al final para no mover ninguna cita `policy.md:N`.
- **`/orchestrator-init`** (`commands/orchestrator-init.md`) detecta tres modos:
  - repo git: pasos 1-6 en la raíz git;
  - raíz multi-repo (sin git, con subcarpetas git a 1 o 2 niveles): pasos 1-6 en cada subrepo y después el paso 7 en la raíz, con `orchestrator.md`, `CLAUDE.md` y `settings.json` de raíz y rutas sensibles con prefijo `<subrepo>/`;
  - sin repo: pasos 1-3 y 5-6, sin el de `.gitignore`.

  También detecta `pubspec.yaml` y, si `orchestrator.md` ya existe, solo corrige datos obsoletos.
- Docs: entrada "relevo de sesión" en `GLOSSARY.md`, cita del ADR 0005 corregida (`orchestrator-init.md:8` → `:13`) y CHANGELOG.

Verificación: `make check` en verde y `verificador` independiente APROBADO.

## Telemetría: carrera en `orch-telemetry` y `maxTurns` (PR #15)

### Síntoma

`/orch-stats` del 2026-10-29 (87 llamadas en 30 días):

| agente | n | tope | estados |
|---|---|---|---|
| `implementador` | 44 | 8 | SIN_ESTADO:22 OK:21 AMPLIAR:1 |
| `verificador` | 35 | 7 | SIN_ESTADO:22 APROBADO:9 RECHAZADO:4 |
| `arquitecto` | 7 | 7 | SIN_ESTADO:4 OK:2 PENDIENTE_APROBACION:1 |

Leído tal cual, sugería que los workers no cumplían el contrato de salida, que el `arquitecto` agotaba siempre `maxTurns` y que RECHAZADO superaba el 30 %.

### Diagnóstico

- Los transcripts de las filas `SIN_ESTADO` sí terminan en una llamada `SubagentHandback` con `ESTADO:` o `VEREDICTO:` en `input.message`, y `summarize()` ya sabía leerla.
- Al reparsear las 51 filas `SIN_ESTADO` con el mismo hook, 50 dan un estado válido (26 OK, 18 APROBADO, 5 RECHAZADO, 1 PENDIENTE_APROBACION).
- Causa: el hook es `async` en `SubagentStop`. Cuando el worker termina con `SubagentHandback`, `last_assistant_message` llega vacío y, a veces, el hook lee el transcript antes de que se escriba esa línea. La fila queda como `SIN_ESTADO` aunque el worker sí informó.
- `tope`: la columna cuenta `turns >= maxTurns`, y `turns` es el número de mensajes del asistente. Las 7 llamadas al `arquitecto` tenían 31-33 turnos con `maxTurns: 30` y terminaron con reporte, así que no se cortaron. Aun así iban siempre en el límite.

### Cambios

- `hooks/orch-telemetry`: si no hay estado ni en `last_assistant_message` ni en el transcript, vuelve a leer el transcript hasta 5 veces (`RETRIES`), esperando `retry_delay()` entre lecturas, y recalcula todo el resumen en la última. `retry_delay()` lee `ORCH_TELEMETRY_RETRY_DELAY` dentro de un `try`: un valor negativo pasa a 0; un valor no numérico, no finito o mayor de 0.5 se queda en 0.5 s. La espera extra máxima es de unos 2,5 s y el hook sigue saliendo siempre con 0. Un reporte JSON del `clasificador` cuenta como estado y no reintenta.
- `tests/test_orch_telemetry.py`: un `sitecustomize` inyectado por `PYTHONPATH` sustituye `time.sleep`; registra cada espera sin dormir y puede añadir la línea `SubagentHandback` al transcript en la llamada N. Tests nuevos:
  - el volcado tardío se recupera;
  - si el estado no aparece nunca: exactamente 5 esperas y `SIN_ESTADO`;
  - con estado ya presente: 0 esperas;
  - con `-1`, `abc`, `nan`, `inf`, `1e308` y `1e6`: rc 0, stderr vacío, 1 línea en el log y cada espera igual a 0 (para `-1`) o 0.5.
- `agents/arquitecto.md` `maxTurns` 30 → 45 y `agents/verificador.md` 25 → 35, con fichas de agente, ADR 0002, `ARCHITECTURE`, `GLOSSARY`, `routing`, `failure-modes`, ADR 0006, el schema de telemetría (citas `orch-telemetry:N-M` desplazadas) y CHANGELOG `[Unreleased]`.

### Verificación

- Gate determinista: `make test`, `make lint`, `make docs-check` y `make typecheck` en verde (288 tests OK, 10 skipped, 3 expected failures).
- `verificador` ciclo 1: RECHAZADO (implementación). Con `ORCH_TELEMETRY_RETRY_DELAY=abc`, el `ValueError` saltaba al importar el módulo, fuera del `try`, y el hook salía con rc 1. Con `-1`, `nan` o `inf`, `time.sleep` fallaba y la fila se perdía. Con `1e6`, el hook podía quedarse colgado.
- `verificador` ciclo 2 (recheck): APROBADO. Quedó una advertencia: el test de valores inválidos dormía de verdad unos 13 s. Se corrigió antes del commit usando el mismo shim.
- CI del PR: 16 checks en verde. Merge squash con `--admin` (etiqueta `security-sensitive`, revisión de code owner requerida).

### Datos e instalación

- Reclasificación de una sola vez de `~/.claude/orchestrator/log.jsonl`: las 50 filas `SIN_ESTADO` recuperables se reescribieron con su estado y `"backfilled": true`. Copia previa en `~/.claude/orchestrator/log.jsonl.bak`. Queda 1 `SIN_ESTADO` real (`Explore`).
- `/orch-stats` después: `implementador` OK:43 AMPLIAR:1; `verificador` APROBADO:26 RECHAZADO:9 (25 %); `arquitecto` OK:5 PENDIENTE_APROBACION:2. `tope`: 8, 2 y 0.
- Antes del merge el hook se copió a mano a `~/.claude/hooks/` (el anterior quedó en `~/.claude/orchestrator/orch-telemetry.bak`). Tras el merge se reinstaló desde `main` (`0aeaa5d`) sin `--force`: solo se actualizaron `docs/INDEX.md` y `docs/audit-pending.md` y se creó `docs/avances.md`. `/orch-doctor`: 9 pass, 0 warn, 0 fail.
- Descartado: añadir a `implementador` un paso de autocomprobación de criterios para bajar RECHAZADO. Con los datos corregidos, RECHAZADO es el 25 %, por debajo del umbral del 30 % de `/orch-stats`.

## Instalación en `~/.claude`

Última reinstalación: 2026-10-30 desde `main` (`0aeaa5d`), ver la sección anterior. La primera fue el 2026-10-29 desde `main` (`c8cdc7e`):

```bash
.venv/bin/python scripts/relevo_install.py install --force --pin-backup
```

- Backup fijado de lo reemplazado: `~/.claude/.relevo-backups/20261029-145316`.
- Manifest 0.2.0 con 41 archivos. Las próximas actualizaciones ya no necesitan `--force`.
- `settings.json`: solo se añadió `SessionStart` → `~/.claude/hooks/orch-resume` para `compact` y `resume`.
- `/orch-doctor`: 9 pass, 0 warn, 0 fail.

Contenido instalado:

| Ruta | Qué es |
|---|---|
| `~/.claude/orchestrator/` | `policy.md`, `routing.json`, `doctor.py`, `render_routing.py`, `stats.py`, `project-template.md`, `log.jsonl` (telemetría) y `docs/` |
| `~/.claude/agents/` | Los 6 workers |
| `~/.claude/commands/` | `orch-doctor.md`, `orch-stats.md` y `orchestrator-init.md` |
| `~/.claude/hooks/` | `block-force-push`, `guard-secrets`, `orch-telemetry` y `orch-resume` |
| `~/.claude/settings.json` | Permisos y registro de hooks |
| `~/.claude/CLAUDE.md` | Importa la política |

## Cómo se trabajó

- Cada fase fue en su propia rama y PR. Las fases 2 y 3 corrieron en sesiones aparte de Claude Code, cada una en su worktree.
- En cada cambio: gate determinista (`make check`: lint, lint de workflows, mypy, tests y comprobaciones de docs) y después un `verificador` con contexto limpio que recibe la petición literal, no el razonamiento del implementador.
- Commits con DCO (`-s`). Ningún commit, push ni merge sin OK explícito del usuario.
- Restricción de todo el trabajo: no relajar ninguna regla de `orchestrator/policy.md`, solo añadir.

Estado de los gates en `main` (`c8cdc7e`): 284 tests OK (10 skipped, 3 expected failures), routing sincronizado, enlaces de 46 archivos Markdown, 8 schemas y fichas de 6 agentes correctos.

## Pendiente

| Tema | Detalle |
|---|---|
| Release 0.2.1 | `[Unreleased]` ya contiene §9, `/orchestrator-init` multi-repo, el reintento de `orch-telemetry` y `maxTurns` 45/35 |
| Copias locales | `~/.claude/orchestrator/log.jsonl.bak` y `~/.claude/orchestrator/orch-telemetry.bak` se pueden borrar cuando `/orch-stats` lleve unos días sin `SIN_ESTADO` nuevos |
| Vigilar `SIN_ESTADO` | Si reaparece con el reintento, los 2,5 s no bastan: valorar leer el estado del payload de `SubagentStop` si Claude Code llega a incluir el handback |
| `/orch-doctor` en raíces multi-repo | `doctor.py` da por hecho una raíz git (`gitignore:work`, `claude-md:import`) y puede avisar sin motivo en una raíz multi-repo sin git |
| Dependabot | PR [#9](https://github.com/Turing0x/relevo/pull/9) (python-dev-tools) y [#10](https://github.com/Turing0x/relevo/pull/10) (github-actions) abiertos |
| audit-pending | #5 a medias (timeout de red e interrupción por el usuario) y #7 (clasificación en línea con opus frente a `clasificador` con otro modelo), a comprobar a mano |
| Medir | Comparar `/orch-stats` dentro de 30 días: llamadas a opus por tarea, `tope` y `SIN_ESTADO` |
| Idea abierta | Las lentes 4R como foco dentro del brief del `verificador` (una sola llamada con más dirección) |
| Limpieza local | El worktree `.claude/worktrees/elegant-haibt-070da9` de la fase 2 sigue en disco; borrarlo necesita aprobación |
