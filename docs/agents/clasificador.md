---
name: clasificador
summary: Clasifica una petición en tipo, riesgo, complejidad y ruta, y devuelve JSON sin ejecutar nada.
model: haiku (effort low, maxTurns 3)
source: ~/.claude/agents/clasificador.md
---
Ficha del worker `clasificador` del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Lee la petición y como máximo 3 archivos, y devuelve un JSON con `tipo`, `riesgo`, `complejidad`, `archivos_estimados`, `ruta`, `necesita_aprobacion` y `motivo` (`~/.claude/agents/clasificador.md:10-15`).

NO ejecuta la tarea, NO edita y NO ejecuta comandos (`~/.claude/agents/clasificador.md:7`, `:10`). NO decide la ruta final: el router recalcula el riesgo final y puede ignorar el JSON (`~/.claude/orchestrator/policy.md:10-11`).

## Cuándo se invoca
Solo cuando la sesión principal no es opus; si lo es, el router clasifica en línea. Ver [../routing.md](../routing.md#paso-1-clasificar) y `~/.claude/orchestrator/policy.md:10`.

## Input
La petición del usuario en el brief. NO ve CLAUDE.md ni la política (`omitClaudeMd: true`, `~/.claude/agents/clasificador.md:8`), por eso lleva su propia copia de la tabla B (`:17-23`) y de la lista de alto riesgo con los mismos números (`:25-31`). Puede leer la config de proyecto `.claude/orchestrator.md` si existe (`:33`). NO ve el historial del chat. Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Solo un JSON. Valores posibles en [../contracts/clasificador-output.schema.json](../contracts/clasificador-output.schema.json).

| Campo | Valores |
|---|---|
| `tipo` | `busqueda`, `mecanica`, `implementacion`, `arquitectura`, `bug_dificil`, `revision` |
| `riesgo` | `bajo`, `medio`, `alto` (alto si toca un elemento 1-5 de la lista de alto riesgo; mínimo medio con el 6; `:30-31`) |
| `complejidad` | 1-5 |
| `ruta` | `en_linea`, `Explore`, `rapido`, `implementador`, `arquitecto`, `verificador` |
| `necesita_aprobacion` | `true`, `false` |

## Tools y permisos
`Read`, `Grep`, `Glob` (`~/.claude/agents/clasificador.md:7`). Sin `Bash`, `Edit`, `Write` ni `Agent`. No puede modificar ni borrar archivos.

## Por qué este modelo
Clasificar es una tarea corta de patrón; haiku a effort low basta. Ver [../decisions/0002-modelo-por-rol.md](../decisions/0002-modelo-por-rol.md).

## Modos de fallo
| Síntoma | Causa probable | Respuesta del orquestador |
|---|---|---|
| No devuelve JSON o devuelve JSON incoherente | Petición ambigua, modelo pequeño | El router clasifica en línea (`~/.claude/orchestrator/policy.md:10`) |
| Riesgo infravalorado | Juicio del modelo | El router usa el máximo con su propio juicio (`~/.claude/orchestrator/policy.md:11`) |
| `ruta` distinta de la tabla B de la política | Copias desincronizadas | Imposible en una instalación desde el repo: las dos copias se generan desde `orchestrator/routing.json` con `scripts/render_routing.py`, y `make docs-check` y `tests/test_repo_consistency.py` fallan en CI si divergen (`~/.claude/orchestrator/policy.md:23`) |
| Lista de alto riesgo distinta de §6bis | Copias desincronizadas | `tests/test_repo_consistency.py` falla en CI |
| Agota 3 turnos | Lee demasiado | Vuelve al router con una nota de límite de turnos y sin `ESTADO`; no se dispara `SubagentStop` y no queda línea en `log.jsonl` (E2E con Claude Code 2.1.312, [../audit-pending.md](../audit-pending.md) #2) |

## Ejemplo
Ilustrativo (no hay trazas reales de este worker en `~/.claude/orchestrator/log.jsonl`).

Input: "renombra `getUser` a `fetchUser` en todo `src/`".
Output:
```json
{"tipo":"mecanica","riesgo":"bajo","complejidad":1,"archivos_estimados":8,"ruta":"rapido","necesita_aprobacion":false,"motivo":"renombrado mecánico en varios archivos"}
```

## Código
- `~/.claude/agents/clasificador.md`
- `~/.claude/orchestrator/policy.md:9-11`, `:23-31`, `:56-63`
