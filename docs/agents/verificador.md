---
name: verificador
summary: Revisa de forma independiente el trabajo de otro ejecutor contra la petición original y devuelve un veredicto.
model: opus (effort high, maxTurns 25)
source: ~/.claude/agents/verificador.md
---
Ficha del worker `verificador` del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Lee el diff real, lo contrasta con los criterios, ejecuta tests/lint/build y busca bugs, casos borde, regresiones, secretos, acciones sensibles no aprobadas y cambios fuera de alcance (`~/.claude/agents/verificador.md:9-11`).

NO edita archivos, tampoco vía `Bash` (`:12`). NO verifica su propio trabajo (`:3`). NO recibe el razonamiento del implementador (`:9`; `~/.claude/orchestrator/policy.md:46`).

## Cuándo se invoca
- Tras el gate determinista en verde, si el riesgo es medio o alto o cambió más de un archivo (`~/.claude/orchestrator/policy.md:45`).
- En rutas marcadas "verificador obligatorio" por la config de proyecto (`~/.claude/orchestrator/project-template.md`).
- Tipo `revision` (`~/.claude/orchestrator/policy.md:26`).

Siempre con contexto limpio, aunque quien implementó fuera opus (`~/.claude/orchestrator/policy.md:45`). Ver [../routing.md](../routing.md#paso-4-verificación-dos-gates).

## Input
Petición original literal del usuario, criterios de aceptación y lista de archivos (`~/.claude/orchestrator/policy.md:46`). Ve CLAUDE.md de usuario y de proyecto. NO ve el historial del chat ni el razonamiento del implementador. Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Texto, máx. 8 hallazgos ordenados por severidad (`~/.claude/agents/verificador.md:13-17`):
- `VEREDICTO: APROBADO | RECHAZADO`
- `Causa: diseño | implementación | —`. Diseño: el enfoque es incorrecto. Implementación: el plan vale pero el código falla.
- `Hallazgos: [severidad] archivo:línea — problema — fix sugerido`
- `Comandos: <comando> → <resultado>`

Schema: [../contracts/verificador-output.schema.json](../contracts/verificador-output.schema.json).

## Tools y permisos
`Read`, `Grep`, `Glob`, `Bash` (`~/.claude/agents/verificador.md:7`). Sin `Edit`, `Write` ni `Agent`.

**Destructivo posible:** con `Bash` puede escribir o borrar. La prohibición de editar (`:12`) es solo de prompt.

## Por qué este modelo
Opus con contexto limpio: la independencia viene del contexto, no del cambio de modelo, y la prioridad es calidad sobre coste. Ver [../decisions/0004-verificacion-dos-gates.md](../decisions/0004-verificacion-dos-gates.md).

## Modos de fallo
| Síntoma | Causa probable | Respuesta del orquestador |
|---|---|---|
| `RECHAZADO`, `Causa: implementación` o dudosa | Código incorrecto | Re-brief al mismo ejecutor (`~/.claude/orchestrator/policy.md:20`) |
| `RECHAZADO`, `Causa: diseño` | Enfoque incorrecto | Replan con `arquitecto` (`~/.claude/orchestrator/policy.md:19`) |
| Segundo `RECHAZADO` en la tarea | — | Parar y reportar (`~/.claude/orchestrator/policy.md:34`) |
| Cualquier veredicto en tarea `revision` | — | Consolidación final, sin re-brief (`~/.claude/orchestrator/policy.md:18`) |
| Sin `Causa` | Incumple el contrato | Se trata como dudosa → re-brief (`~/.claude/orchestrator/policy.md:20`) |

## Ejemplo
Real en métricas. `~/.claude/orchestrator/log.jsonl` registra 4 llamadas el 2026-10-22: 3 `APROBADO` y 1 `RECHAZADO`. Media: 6,8 turnos, 118 s, opus-5-5, effort high. El contenido de esas revisiones no se reproduce.

Forma de la salida (ilustrativa):
```
VEREDICTO: RECHAZADO
Causa: implementación
Hallazgos: [alta] src/validators/user.js:14 — acepta "a@b" sin dominio — usar regex con TLD
Comandos: pnpm test → 42 passed
```

## Código
- `~/.claude/agents/verificador.md`
- `~/.claude/orchestrator/policy.md:18-20`, `:26`, `:44-46`
