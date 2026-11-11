# 0015 — Recorte de salida de tests con un hook

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
Una salida larga de tests o build entra en el contexto del agente que la ejecuta y se relee como `cache_read` en cada turno posterior (ver [0014](0014-coste-por-rol-y-contexto.md)). El router la corre en línea y varios workers repiten comandos de test ([0013](0013-calidad-del-implementador.md)). Las dos formas de recortar son pedirlo al modelo (texto de prompt, no se impone) o reescribir el comando con un hook `PreToolUse` y `updatedInput`.

## Decisión
- Hook `~/.claude/hooks/trim-test-output` (PreToolUse, matcher `Bash`, `timeout: 5`). **Opt-in:** el instalador lo copia pero `templates/settings.example.json` no lo registra; se activa añadiendo la entrada `PreToolUse` `Bash` a `settings.json` (README). Es un wrapper, no un `| tail`: reescribe el comando a `<python> <ruta-real-del-hook> --run -- <argv original>`. En modo `--run` ejecuta el argv con `subprocess.Popen` (sin shell, mismo cwd, entorno y stdin), captura stdout y stderr, y sale con el mismo exit code del hijo (señal → 128+n; `hooks/trim-test-output:91-109`).
- Selección por regex estricta (`hooks/trim-test-output:8-38`): tras `shlex.split`, el comando entero debe ser `make (check|test|lint|typecheck)`, `pytest`/`py.test`, `python|python3|.venv/bin/python -m (pytest|unittest)`, `uv run pytest`, `(npm|pnpm|yarn|bun) test`, `(npm|pnpm) run test`, `go test` o `cargo test`, con el resto de argumentos solo en `[A-Za-z0-9_./:=,@+-]`. Se rechaza si el texto crudo contiene `` ;&|<>$`(){}\n'"\ ``, `*` o `~`, si un token contiene `.env`, `..` o `watch`. Una asignación de entorno delante (`RELEVO_FULL_OUTPUT=1 make check`) no casa: es la vía de exclusión puntual. `RELEVO_TRIM_DISABLE=1` en el `env` de settings lo desactiva globalmente. El comando reescrito empieza por la ruta de python, así que no casa otra vez.
- Salida recortada: ≤120 líneas, tal cual. Si no, el log íntegro va a `tempfile.mkstemp(prefix="relevo-test-")` (0600, `$TMPDIR`); con exit ≠ 0 se imprimen las líneas con `FAIL|ERROR|Error|error:|Traceback|AssertionError|panic:|^E  |failed|✗` (máx 150, sin duplicados, ±1 línea de contexto) y las últimas 60; con exit 0, las últimas 30. Si crear o escribir el log falla, imprime la salida íntegra y conserva el exit del hijo. Al crear un log nuevo borra los `relevo-test-*.log` propios (mismo directorio) de más de 24 h, sin propagar errores. Cierra con `[relevo] salida recortada: N líneas, exit X, completa en <ruta>` (`hooks/trim-test-output:54-89`).
- Seguridad: el hook nunca emite `permissionDecision` ni sale con 2; no puede aprobar nada ni saltarse `ask`. Cualquier excepción o JSON inválido termina sin salida y exit 0 (no-op). Los comandos que casan no pueden ser push ni leer `.env` (charset y tokens), así que `block-force-push` y `guard-secrets` no cambian.
- Doctor: `trim-test-output` entra en `HOOKS` (debe existir y ser ejecutable) pero no en `EXPECTED_HOOKS`; si está registrado, `hooks:registered` lo anota como opt-in.
- Tabla B: la fila `mecanica` pasa a "salida ≤80 líneas (tests/build: salida recortada solo si `trim-test-output` está activado)" (`~/.claude/orchestrator/policy.md:29`).

## Por qué
`| tail` depende de `pipefail` y del shell del usuario (zsh o bash): perdería el exit code del comando, y el verde/rojo del gate 1 es lo que el router usa para decidir. El wrapper conserva el exit code por construcción, no usa shell y su regex deja fuera todo lo que no sea un comando de test conocido.

## Alternativas
- `| tail -n 60`. Descartada: pierde el exit code sin `pipefail`, no recorta por contenido y exige shell.
- Instrucción en el prompt de cada worker. Descartada: no se impone y se repite en cada rol.
- Recortar toda salida de Bash. Descartada: riesgo de ocultar información de comandos que no son de test.

## Consecuencias
- Resultado E2E (`make e2e`, `tests/e2e/test_e2e_claude.py`, API falsa): `[VERIFICAR]` resuelto. (1) Claude Code aplica `updatedInput` sin `permissionDecision`. (2) Los permisos se evalúan sobre el comando **ya reescrito**: aunque `allow` cubra el original, o sea un `Bash` genérico, el comando reescrito pide aprobación (`test_trim_hook_rewritten_command_needs_its_own_permission`); no se pudo evitar sin emitir `permissionDecision`, que el hook no debe hacer. (3) Las reglas `deny` siguen aplicando (`test_deny_rule_still_applies_to_a_command_the_trim_hook_would_rewrite`).
- Por eso la decisión es **opt-in**: activado por defecto, cada comando de test generaría un prompt nuevo (o lo decidiría el clasificador en modo auto), peor que la salida larga que evita. Quien lo active acepta esos prompts.
- Una causa de fallo sin `FAIL`/`Error`/`Traceback` puede quedar fuera del extracto; el log íntegro y `RELEVO_FULL_OUTPUT=1` lo cubren (`docs/failure-modes.md`).
- La exclusión depende de que el modelo anteponga `RELEVO_FULL_OUTPUT=1 `; los usuarios y el `verificador` deben saberlo.
- Cambia lo que ve el modelo, no los permisos: riesgo alto por tocar un hook y el instalador (6bis-2, 6bis-5), cubierto por `tests/test_trim_test_output.py`, `tests/test_install.py` y `tests/test_doctor.py`.
