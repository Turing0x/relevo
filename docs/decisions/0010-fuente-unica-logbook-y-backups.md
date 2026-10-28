# 0010 — Fuente única de la tabla B, logbook de tarea y backups con retención

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
Tres puntos débiles de estructura, todos de la comparativa `docs/Gentle AI vs relevo qué aprender.md` del repo (fase 2, ideas 1, 11 y 13):
- La tabla B vivía dos veces, en la política y en `clasificador` (que corre con `omitClaudeMd` y no ve la política). Solo la fila `busqueda` tenía test; el resto podía divergir sin que nada lo detectara ([../failure-modes.md](../failure-modes.md)).
- Los contadores de presupuesto (`arquitecto` 1, ciclos 2) eran texto en el contexto del router. Una compactación o una sesión reanudada podían perderlos, y con ellos el límite de §3 (check #6 de [../audit-pending.md](../audit-pending.md)).
- El instalador creaba un directorio de backup por ejecución sin retención, y al fusionar `settings.json` lo reescribía como JSON: un archivo con comentarios no se podía leer, y uno con claves duplicadas perdía en silencio todas menos la última.

## Decisión
Solo se añaden reglas y comprobaciones; ninguna se relaja.
- **Fuente única de la tabla B.** `orchestrator/routing.json` del repo guarda las filas y todos los umbrales, incluidos los del presupuesto de evidencia de `busqueda` (ADR 0009). `scripts/render_routing.py` reescribe el texto entre `<!-- relevo:routing:begin -->` y `<!-- relevo:routing:end -->` en `orchestrator/policy.md` §2B (`~/.claude/orchestrator/policy.md:24-32`) y en `agents/clasificador.md` (`~/.claude/agents/clasificador.md:18-24`). Valida que los seis tipos aparezcan una vez, que cada umbral sea un entero positivo usado por alguna fila y que cada umbral de una fila aparezca en las dos copias. Con `--check` no escribe y falla si alguna copia diverge; va en `make docs-check` y, por tanto, en CI (workflow Docs). `tests/test_repo_consistency.py` (`PolicySyncTests`) compara las copias con el render y comprueba que una copia editada a mano hace fallar el `--check`. El JSON no se instala: lo instalado es el texto ya generado.
- **Logbook de tarea** (`~/.claude/orchestrator/policy.md:38`). El router crea `<raíz git>/.claude/work/<tarea>/estado.md` si la tarea usa `arquitecto`, tiene más de un tramo o no se podría retomar solo con la petición y el diff. Campos: petición literal, ruta, `arquitecto: N/1`, `ciclos: N/2`, tramos con estado, último veredicto y siguiente paso. Se actualiza tras cada worker, gate o veredicto y se cierra con `estado: cerrada` como última línea (se admite viñeta, cita o énfasis markdown). Tras compactar o reanudar, sus contadores mandan sobre la memoria del chat y nunca bajan. Sin repo git no se crea.
- **Hook `orch-resume`** (`~/.claude/hooks/orch-resume`, Python stdlib). En `SessionStart` con los matchers `compact` y `resume` (dos grupos, timeout 5 s) imprime el `estado.md` abierto más reciente de la raíz git de `cwd`, marcado como dato de estado y no como instrucciones, y lista las otras tareas abiertas. Solo lectura, siempre sale con 0. No reinyecta nada si `.claude/work/` no está en el `.gitignore` de la raíz; descarta los `estado.md` versionados en git (`git ls-files`, timeout 2 s; si git no responde, no reinyecta ninguno), los symlinks (también `.claude`, `.claude/work` o el directorio de la tarea; abre directorio y archivo con `O_NOFOLLOW`), lo que no sea un archivo regular (un FIFO se abre con `O_NONBLOCK` y se descarta, sin bloquear), los archivos de otro usuario y los de más de 64 KiB; trunca la salida a 6000 caracteres. El instalador lo copia y lo registra con el resto de hooks, y el manifest lo recoge para la desinstalación. Para eso la fusión de hooks admite el mismo comando bajo varios matchers de la plantilla, pero sigue sin añadir un comando que el usuario ya tenga en ese evento.
- **Backups del instalador** (`scripts/relevo_install.py`). Cada backup guarda `.relevo-backup.json` con el sha256 de cada archivo. Si el conjunto coincide con un backup anterior, se reutiliza ese en vez de crear otro; el manifest se compara sin su hora de instalación. Tras instalar o desinstalar se conservan los 5 backups usados más recientemente. Nunca se borran los fijados (`.pinned`, con `install --pin-backup` o `relevo_install.py backups --pin NOMBRE`), los que guardan un original de `--force` que el manifest restaurará, ni el de la ejecución en curso. La poda solo toca directorios con nombre de marca de tiempo dentro de `.relevo-backups/` que no sean symlinks.
- **Merge estricto de `settings.json`.** Si el archivo tiene comentarios (`//` o `/*` fuera de una cadena) o claves duplicadas a cualquier profundidad, instalar y desinstalar fallan antes de escribir nada, con la línea o la clave y el remedio.

## Por qué
- Generar desde datos elimina la clase de fallo, no solo la detecta: un umbral se cambia en un sitio y el texto de las dos copias sale igual.
- Un contador en disco no depende de la compactación. El hook solo lo lee y lo imprime; la regla de que los contadores nunca bajan impide usar el logbook para saltarse el presupuesto.
- El hook mete texto en el contexto del router, así que solo lo hace con archivos que el propio router escribió: `.claude/work/` ignorado por git y el `estado.md` concreto sin versionar. Un repo clonado no puede colarlo ni con `git add -f`, porque ese archivo sí aparece en `git ls-files`.
- Fallar ante JSONC o claves duplicadas cambia una pérdida silenciosa de configuración del usuario por un error con remedio (`--no-settings`).

## Alternativas
- Mantener las copias a mano con un test por fila. Descartada: cada fila nueva necesita su test y el texto puede seguir divergiendo en lo que el test no mira.
- Que `clasificador` lea la política. Descartada: correr con `omitClaudeMd` es lo que lo hace barato ([0002-modelo-por-rol.md](0002-modelo-por-rol.md)).
- Memoria externa (Engram) para el estado. Descartada como requisito por ser un servicio externo; puede documentarse como integración opcional.
- Un solo grupo `SessionStart` con matcher `compact|resume`. Descartada: no está documentado que ese evento acepte alternativas en el matcher, y dos grupos funcionan con cualquier interpretación.
- Preservar comentarios con un parser JSONC propio. Descartada: más código en una pieza sensible; con `--no-settings` el usuario fusiona a mano.
- Backups `tar.gz` como gentle-ai. Descartada: un directorio de archivos se restaura a mano sin herramientas y es lo que ya usaba el manifest.

## Consecuencias
- Cambiar un umbral o una fila de la tabla B exige editar `routing.json` y ejecutar `python3 scripts/render_routing.py`; editar las copias a mano rompe CI.
- El check #6 de [../audit-pending.md](../audit-pending.md) se cierra por diseño. El check #8 (que Claude Code añade al contexto la salida de `orch-resume` en `compact` y `resume`) lo cierra el E2E de [0011](0011-doctor-y-e2e.md); si una versión futura deja de hacerlo, el logbook sigue en disco y el router puede leerlo a mano.
- Sigue sin enforcement: crear y actualizar el logbook es texto de política ([0001-politica-con-refuerzo-duro.md](0001-politica-con-refuerzo-duro.md)). El hook solo lo reinyecta.
- El instalador borra backups antiguos sin preguntar. Lo limita a su propio directorio, conserva 5, respeta los fijados y nunca borra un original que vaya a restaurar.
- Un `settings.json` con comentarios que antes daba "not valid JSON" ahora da un error que nombra la línea y la salida `--no-settings`.
