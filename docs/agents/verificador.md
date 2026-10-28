---
name: verificador
summary: Revisa de forma independiente el trabajo de otro ejecutor contra la petición original y devuelve un veredicto.
model: opus (effort high, maxTurns 25)
source: ~/.claude/agents/verificador.md
---
Ficha del worker `verificador` del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Lee el diff real, lo contrasta con los criterios, ejecuta tests/lint/build y busca bugs, casos borde, regresiones, secretos, acciones sensibles no aprobadas y cambios fuera de alcance (`~/.claude/agents/verificador.md:9-11`).

- **Severidad con base.** Bloqueante es un defecto causado por el cambio que no se reproduce en `base_commit`; para comprobarlo usa una copia temporal (`mktemp -d` + `git archive`), nunca el workspace. Siempre bloqueante: criterio de aceptación incumplido, regresión introducida por el fix de un ciclo anterior, ignorar en silencio una opción explícita, cambiar una salida que nadie pidió cambiar, secretos o acción sensible no aprobada. Lo que ya fallaba en la base es advertencia (`:13`).
- **Precision gate.** Solo hallazgos defendibles con evidencia (`archivo:línea`, comando o salida); nada de estilo salvo que oculte un defecto. Limpio: `Hallazgos: ninguno` (`:14`).
- **Modo recheck.** Revisa solo `recheck_findings` y marca cada uno `resuelto` o `persiste`; todo hallazgo nuevo es advertencia. `RECHAZADO` solo si persiste alguno o aparece uno de los "siempre bloqueante" (`:15`).

NO edita archivos, tampoco vía `Bash` (`:12`). NO verifica su propio trabajo (`:3`). NO recibe el razonamiento del implementador (`:9`; `~/.claude/orchestrator/policy.md:49`).

## Cuándo se invoca
- Tras el gate determinista en verde, si el riesgo es medio o alto o cambió más de un archivo (`~/.claude/orchestrator/policy.md:48`).
- En rutas marcadas "verificador obligatorio" por la config de proyecto (`~/.claude/orchestrator/project-template.md`).
- Tipo `revision` (`~/.claude/orchestrator/policy.md:27`).
- En `modo: recheck` en el 2º ciclo tras `RECHAZADO` con `Causa: implementación` o dudosa; tras un replan, revisión completa (`~/.claude/orchestrator/policy.md:36`).

Siempre con contexto limpio, aunque quien implementó fuera opus (`~/.claude/orchestrator/policy.md:48`). Ver [../routing.md](../routing.md#paso-4-verificación-dos-gates).

## Input
Petición original literal del usuario, criterios de aceptación, lista de archivos, `base_commit` y `modo` (`normal` | `recheck`, con `recheck_findings`) (`~/.claude/orchestrator/policy.md:49`, `~/.claude/agents/verificador.md:9`). Ve CLAUDE.md de usuario y de proyecto. NO ve el historial del chat ni el razonamiento del implementador. Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Texto, máx. 8 hallazgos ordenados por severidad (`~/.claude/agents/verificador.md:16-21`):
- `VEREDICTO: APROBADO | RECHAZADO`. `RECHAZADO` solo con ≥1 bloqueante.
- `Causa: diseño | implementación | —`. Diseño: el enfoque es incorrecto. Implementación: el plan vale pero el código falla.
- `Hallazgos: [bloqueante|advertencia] archivo:línea — problema — fix sugerido | ninguno`
- `Recheck: <hallazgo previo> — resuelto | persiste` (solo en modo recheck)
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
| Segundo `RECHAZADO` en la tarea | — | Parar y reportar (`~/.claude/orchestrator/policy.md:36`) |
| Hallazgo nuevo en recheck | Defecto fuera de `recheck_findings` | Advertencia; no consume ciclo; va a la consolidación final (`~/.claude/orchestrator/policy.md:36`, `:66`) |
| Sin `base_commit` en el brief | Brief incompleto | No especificado `[VERIFICAR]` |
| Cualquier veredicto en tarea `revision` | — | Consolidación final, sin re-brief (`~/.claude/orchestrator/policy.md:18`) |
| Sin `Causa` | Incumple el contrato | Se trata como dudosa → re-brief (`~/.claude/orchestrator/policy.md:20`) |

## Ejemplo
Real en métricas. `~/.claude/orchestrator/log.jsonl` registra 4 llamadas el 2026-10-22: 3 `APROBADO` y 1 `RECHAZADO`. Media: 6,8 turnos, 118 s, opus-5-5, effort high. El contenido de esas revisiones no se reproduce.

Forma de la salida (ilustrativa):
```
VEREDICTO: RECHAZADO
Causa: implementación
Hallazgos: [bloqueante] src/validators/user.js:14 — acepta "a@b" sin dominio — usar regex con TLD
Comandos: pnpm test → 42 passed
```

## Código
- `~/.claude/agents/verificador.md`
- `~/.claude/orchestrator/policy.md:18-20`, `:27`, `:36`, `:47-50`
