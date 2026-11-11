# 0014 — Coste por rol y contexto

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
`/orch-stats` no mostraba dinero, solo tokens. Con la tabla de precios nueva (M8, abajo) la salida real de los últimos 30 días, a precio de lista y sin thinking (infraestima), es:

| Agente | Llamadas | `$~` |
|---|---|---|
| `implementador` | 129 | ~105 |
| `verificador` | 122 | ~76 |
| `arquitecto` | 23 | ~67 (2,91 por llamada) |
| Total | — | ~248 |

El `verificador` de nivel 2 rechaza el 35 % de las veces (14 de 40). Telemetría del `arquitecto` (22 runs): con effort `medium` los turnos fueron 6, 6, 8, 9, 9, 10, 16, 18 y 51 (mediana ≈ 9, p90 ≈ 18); el de 51 ya superaba `maxTurns: 45`. Contexto por turno entre 62k y 210k. El `cache_write` del `arquitecto` va de 100k a 780k por run y, con TTL de 1 h (2× entrada), es el mayor componente junto con `cache_read`. Lo leído en línea por el router queda en su contexto opus y se relee como `cache_read` en cada turno posterior.

Restricción: ninguna regla de la política se relaja; solo se añade o endurece. Precios de lista usados ($/MTok): opus entrada 4, salida 20, `cache_read` 0,20; sonnet 2, 10, 0,10; haiku 0,10, 0,50 (≤100k de prompt) y `cache_read` 0,01. El `cache_read` de haiku no figura en la tabla de la fuente: es 0,1× supuesto `[VERIFICAR]`.

## Decisión
- **M1, menos lectura en línea.** Umbrales de la tabla B en `orchestrator/routing.json` (fuente única): `busqueda` en línea solo con ≤2 archivos y ~5k tokens (antes ≤3 y ~10k); `Explore` también si en línea ya van >3 búsquedas secuenciales (antes >5); `mecanica` en línea con salida ≤80 líneas (antes "corta"; tests/build llegan ya recortados por [0015](0015-recorte-de-salida-de-tests.md)). Regenerado en `~/.claude/orchestrator/policy.md:28-29` y `~/.claude/agents/clasificador.md`. Cálculo: 10k tokens en línea × 40 turnos son 400k de `cache_read` (0,08 $) más 10k de `cache_write` 1 h (0,08 $), unos 0,16 $ por búsqueda; un `Explore` haiku de ~50k de contexto cuesta menos de 0,01 $ y devuelve ~1k. Nada se relaja: baja lo que se permite en línea; "`Explore` insuficiente → seguir en línea" y la comprobación del router (§5.3) siguen cubriendo la calidad de haiku.
- **M3, experimento: `verificador` nivel 1 en sonnet** (`~/.claude/orchestrator/policy.md:48`). El router pasa `model: "sonnet"` solo si el nivel es 1 y el modo `normal`; el frontmatter sigue en `model: opus`. Si devuelve `Nivel: 2 (escalado)`, el veredicto se descarta (no consume ciclo) y se relanza en opus con nivel 2 y `motivo: escalado`, así que nivel 2 nunca lo decide sonnet. Nivel 2, `recheck`, replan, riesgo alto, salida de `arquitecto`, ruta "verificador obligatorio" y `revision` van siempre en opus. Un proyecto puede fijar `verificador_modelo: opus` en `.claude/orchestrator.md` para desactivarlo (`orchestrator/project-template.md:17`). Solo hay dos runs de nivel 1 en el histórico (1 RECHAZADO): el experimento es el medio de obtener datos.
- **Criterio de reversión (M3).** Volver a opus a los 30 días, o antes si (a) un defecto llega a `main` en un diff aprobado por un nivel 1 sonnet (lo anota el usuario o el router en `docs/avances.md` o el HANDOFF), (b) ≥30 % de los nivel 1 sonnet acaban en `escalado` (el ahorro desaparece) o (c) >10 % salen `SIN_ESTADO` o fuera de contrato. Con n<10 a los 30 días: prorrogar, no concluir.
- **M4, `arquitecto` `maxTurns` 45 → 35** (`~/.claude/agents/arquitecto.md:6`). 35 cubre todas las runs `medium` salvo el outlier de 51 y deja ~2× de margen sobre el p90. No se fija `autoCompactWindow`: con 62k-210k por turno, el mínimo permitido (100k) compactaría la mayoría de runs a mitad de diseño y cualquier valor ≥250k no se alcanza nunca. Como un corte por `maxTurns` no deja `ESTADO` ni telemetría ([0011](0011-doctor-y-e2e.md)), el prompt pide escribir pronto el esqueleto del plan en `.claude/work/plan-<tarea>.md` y completarlo por tramo (`~/.claude/agents/arquitecto.md:13`), y el router anota en `estado.md` cualquier vuelta por límite. Reversión: con ≥2 vueltas por límite anotadas en 30 días, subir a 40.
- **M5, `## 10. Compact instructions`** (`~/.claude/orchestrator/policy.md:80-81`): al compactar el router conserva literal la petición del usuario, la ruta de `estado.md`, `arquitecto: N/1`, `ciclos: N/2`, `base_commit`, el tramo en curso, el último veredicto con sus bloqueantes y el siguiente paso, y descarta salidas de herramientas ya resumidas. Vive en la política (se instala y actualiza con ella; los workers la ignoran por la línea 2). No va en `templates/CLAUDE.md.example`: `plan_claude_md` no reescribe un bloque ya instalado, no llegaría a instalaciones existentes y duplicaría. `[VERIFICAR]`: que `/compact` recibe el texto de un archivo importado; no hay E2E que lo compruebe todavía. Plan B si no llega: bloque en `CLAUDE.md.example` más aviso de `/orch-doctor` para bloques antiguos; no implementado.
- **M7, cierre de tarea** (`~/.claude/orchestrator/policy.md:78`): con la tarea cerrada (§7) y lo siguiente sin relación, el router sugiere `/rename <tarea>` y `/clear` (coste 0) en vez de `/compact`; con trabajo a medias, primero `HANDOFF.md`; se retoma con `/resume`. No se toca §7. `orchestrator/statusline.py` (opcional, documentado en el README) muestra `ctx NN% · cache: hit|miss|frío`; el instalador lo copia pero nunca registra `statusLine`.
- **M8, `/orch-stats` con coste** (`orchestrator/stats.py:13-30`): tabla `PRICES` única por id de modelo y `CACHE_WRITE_MULT = 2.0` (TTL 1 h de Claude Code). Coste por registro = entrada + `cache_write`·2× entrada + `cache_read` + salida estimada. Columna `$~`, línea `Total estimado` y bloque del `verificador` por (nivel, modelo) con n, RECHAZADO, %, `escalado` y `$~`. Modelo desconocido: sin coste y se cuenta como "registros sin precio".
- **Doctor** (`orchestrator/doctor.py:387-474`): `env` avisa si `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` está activo (anula el `model` de cada rol); check nuevo `claude:version` avisa con Claude Code <2.1.251, o si no puede saberlo. Nunca `fail`.

## Por qué
La partida grande es `implementador` + `verificador` + `arquitecto`; solo `verificador` y lo leído en línea se pueden bajar sin quitar revisión. M1 y M3 mueven trabajo a modelos más baratos solo donde el riesgo es bajo y hay red (comprobación del router, escalado, reversión medible). M4 y M5 acotan el contexto que se relee. M8 hace medible todo lo anterior.

## Alternativas
- `autoCompactWindow` en `arquitecto`. Descartada (ver M4): compacta a mitad de diseño o no actúa.
- Sonnet también en nivel 2 o en `recheck`. Descartada: nivel 2 rechaza el 35 % y es donde la revisión más vale; `recheck` es barato (mediana 4 turnos) y es el último ciclo.
- `# Compact instructions` en `templates/CLAUDE.md.example`. Descartada (ver M5).
- Subir los umbrales en línea para ahorrar workers. Descartada: lo leído en línea se paga en cada turno posterior.

## Consecuencias
- Medir a 30 días con `/orch-stats`: coste total antes/después, bloque nivel × modelo del `verificador`, uso de `Explore` y `rapido`, vueltas por tope del `arquitecto`.
- El `# VERIFICAR` del precio `cache_read` de haiku y la fecha de la tabla (2026-11-03) obligan a revisar `PRICES` si cambian los precios. El TTL real no consta en la telemetría: se asume 1 h.
- `$~` infraestima: la salida estimada no cuenta thinking.
- Texto de prompt y política: sin enforcement más allá de los tests de consistencia ([0001](0001-politica-con-refuerzo-duro.md)).
- `[VERIFICAR]` que sonnet en nivel 1 mantiene la calidad: no medido.
