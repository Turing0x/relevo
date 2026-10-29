# 0011 — `/orch-doctor` y E2E con modelo falso

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
Fase 3 de la comparativa `docs/Gentle AI vs relevo qué aprender.md` del repo (ideas 12 y 14):
- Nada comprobaba una instalación ya hecha. Un hook sin permiso de ejecución, un `settings.json` editado a mano o una tabla B retocada en `~/.claude` solo se notaban cuando algo fallaba en una sesión real ([../failure-modes.md](../failure-modes.md)).
- Varias preguntas sobre el comportamiento de Claude Code ([../audit-pending.md](../audit-pending.md) #1-#5 y #8) solo se podían responder a mano en una sesión nueva, y los tests ejecutaban los hooks con un JSON fabricado, nunca desde Claude Code.
- `[VERIFICAR]` de la comparativa: que Claude Code acepta `ANTHROPIC_BASE_URL` hacia un servidor local y ejecuta hooks reales. Verificado con Claude Code 2.1.312.

## Decisión
Solo se añaden herramientas y comprobaciones; ninguna regla de `~/.claude/orchestrator/policy.md` cambia.
- **`~/.claude/orchestrator/doctor.py`** (Python stdlib, 3.9+) y el comando `/orch-doctor` (`~/.claude/commands/orch-doctor.md`). Nueve comprobaciones con id estable (`~/.claude/orchestrator/doctor.py:598-608`), cada una con estado `pass`, `warn` o `fail` y, si no pasa, un remedio:
  - `python:version`: el intérprete y el `python3` del PATH, ≥3.9.
  - `frontmatter:valid`: agentes (`name`, `description`, `model`, `effort`, `maxTurns`) y comandos; un agente de proyecto con nombre de worker es `warn` (§8).
  - `hooks:executable`: los cuatro hooks existen, son archivos regulares, ejecutables y no escribibles por otros (`o+w` es `fail`).
  - `hooks:registered`: cada hook está en su evento con un matcher que cubre lo que debe, incluido `orch-resume` en `SessionStart` `compact` y `resume`; `disableAllHooks` en el usuario o el proyecto es `fail`.
  - `env`: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` distinto de `1` es `fail`; `CLAUDE_CODE_SUBAGENT_MODEL` distinto de `sonnet`, `warn`.
  - `manifest:drift`: un archivo del manifest que falta o una regla `deny` quitada es `fail`; un archivo modificado o una regla `ask` quitada, `warn`.
  - `claude-md:import`: el `CLAUDE.md` global importa la política y, si el proyecto tiene `.claude/orchestrator.md`, su `CLAUDE.md` lo importa.
  - `gitignore:work`: `.claude/work/` en el `.gitignore` de la raíz git, con el mismo patrón que `orch-resume`.
  - `routing:sync`: la tabla B instalada coincide con `routing.json`.

  Sale con 1 si alguna comprobación falla. Solo lee archivos y ejecuta `python3` para saber su versión: nunca aplica un remedio, y el comando prohíbe al router hacerlo sin aprobación (§6). Una excepción dentro de una comprobación se informa como `fail` de esa comprobación sin ocultar las demás.
- **`routing:sync` reutiliza `scripts/render_routing.py`.** El instalador copia `orchestrator/routing.json` y `scripts/render_routing.py` a `~/.claude/orchestrator/`, y el doctor compara el texto entre marcadores de `policy.md` y `clasificador.md` instalados con lo que renderiza el JSON instalado. Cambia la consecuencia de [0010](0010-fuente-unica-logbook-y-backups.md) "el JSON no se instala": se instala, pero solo lo usa el diagnóstico.
- **E2E con modelo falso** (`tests/e2e/`, repo). `fake_api.py` es un servidor HTTP stdlib en `127.0.0.1` que imita `POST /v1/messages` (también en streaming SSE) con respuestas guionizadas por conversación y turno, y registra cada petición. `test_e2e_claude.py` instala relevo en un `HOME` temporal, crea un repo git con un remoto local y un `.env` con un canario, y ejecuta `claude -p` con `ANTHROPIC_BASE_URL` apuntando al servidor y una API key falsa. Sin red externa, sin key real y sin coste.
- **Qué comprueba el E2E** (Claude Code 2.1.312):
  - Un force push guionizado llega a `block-force-push`, que lo bloquea; el remoto no cambia.
  - `Read` de `.env`, `cat .env` y un `Grep` del repo no envían el canario al modelo; `guard-secrets` responde en el `cat`.
  - Un worker que termina con un reporte deja una línea en `log.jsonl` con su agente, modelo y estado.
  - El `Explore` de relevo sustituye al integrado y corre en haiku con effort `low` (#1, #3).
  - Con profundidad 1, un subagente sin `disallowedTools` no recibe la herramienta `Agent` (#4).
  - Un worker que llega a `maxTurns` vuelve al router con una nota de límite y sin `ESTADO` (#2). Uno cuya petición falla con un error 400 vuelve con "Agent terminated early due to an API error" (#5, parcial). En ninguno de los dos se dispara `SubagentStop`.
  - La salida de `orch-resume` llega al contexto con `--resume` y tras `/compact`, cada matcher por separado y con un control negativo (#8).
- **Opcional y fuera de CI.** `make e2e` (no forma parte de `make check`) fija `RELEVO_E2E=1`; sin esa variable o sin el ejecutable `claude` (o `RELEVO_CLAUDE_BIN`) los tests se saltan. No hay job de CI.
- **`orch-resume` recorre `.claude/work` por descriptores.** `.claude`, `work`, el directorio de la tarea y `estado.md` se abren cada uno relativo al fd de su padre con `O_NOFOLLOW`, y el directorio se lista con `os.listdir(fd)` (`~/.claude/hooks/orch-resume:53-108`). Antes se comprobaba `islink` por ruta y después se recorría por ruta, con una ventana TOCTOU entre ambas. Sin `O_NOFOLLOW` o sin `dir_fd` no reinyecta nada.

## Por qué
- Un diagnóstico de solo lectura convierte en comprobaciones repetibles varias filas de [../failure-modes.md](../failure-modes.md) que antes solo se descubrían al fallar, sin arriesgar la configuración del usuario: el remedio queda en manos humanas, como cualquier acción de §6.
- Reutilizar `render_routing.py` evita una segunda implementación de la tabla B que pudiera divergir.
- El E2E ejercita los hooks desde Claude Code real, con el JSON que de verdad les llega, y responde con evidencia preguntas que antes eran `[VERIFICAR]`.

## Alternativas
- Que el doctor aplique los remedios (`--fix`). Descartada: tocar `settings.json`, hooks o permisos es una acción sensible (§6) y el doctor perdería la garantía de solo lectura.
- Un job de CI para el E2E. Descartada por ahora: exige instalar el CLI de Claude Code en CI con `npm` (una dependencia nueva fuera de `requirements-dev.txt`) y nombrarlo en un workflow, y `tests/test_workflows.py` impide a propósito que un workflow mencione `anthropic`. Relajar ese test para un job opcional no compensa; el E2E se ejecuta en local con `make e2e`.
- Simular Claude Code en vez de ejecutarlo. Descartada: el valor del E2E está en observar el comportamiento real de la versión instalada.
- Duplicar el render de la tabla B dentro de `doctor.py`. Descartada: dos implementaciones del mismo render pueden divergir.

## Consecuencias
- Cerrados por E2E con Claude Code 2.1.312: #1, #2, #3, #4 y #8 de [../audit-pending.md](../audit-pending.md). #5 queda parcial: cubre el error de API, no un timeout ni una interrupción del usuario.
- Hallazgo: `SubagentStop` no se dispara cuando un worker se detiene por `maxTurns` o por un error de API, así que `orch-telemetry` no escribe nada y la columna `tope` de `/orch-stats` no puede contar esos casos. Además, en `claude -p` el hook `async` no llega a correr antes de que el proceso salga: no hay telemetría en modo headless. `test_worker_report_is_logged_by_orch_telemetry` registra el hook sin `async` en su `HOME` temporal para poder leer la línea. Corregirlo (hook síncrono o otra fuente de datos para `tope`) queda como trabajo aparte.
- El E2E depende de una versión concreta de Claude Code y de los textos que devuelve (`400`, la nota de límite de turnos). Si un test cambia de resultado al actualizar Claude Code, hay que revisar este ADR, [../failure-modes.md](../failure-modes.md) y [../audit-pending.md](../audit-pending.md), no solo el test.
- Una instalación anterior no tiene `routing.json` ni `render_routing.py`: `routing:sync` da `warn` hasta reinstalar.
- El instalador copia tres archivos más (`doctor.py`, `routing.json`, `render_routing.py`) y el comando `orch-doctor.md`; el manifest los recoge y la desinstalación los quita.
