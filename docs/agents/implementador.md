---
name: implementador
summary: Implementa features o fixes acotados de 1-5 archivos según un brief con criterios de aceptación.
model: sonnet (effort high, maxTurns 40)
source: ~/.claude/agents/implementador.md
---
Ficha del worker `implementador` del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Implementa el objetivo del brief en los archivos permitidos, sigue el estilo del código vecino y ejecuta el comando de verificación (`~/.claude/agents/implementador.md:9-11`). También ejecuta cada tramo de un plan de `arquitecto` (`~/.claude/orchestrator/policy.md:21`, `:29`).

NO toca archivos fuera del brief: devuelve `AMPLIAR` (`:10`). NO toma decisiones de diseño: devuelve `ESCALAR` (`:13`). NO ejecuta acciones sensibles: devuelve `PENDIENTE_APROBACION` (`:12`). NO lanza subagentes (`disallowedTools: Agent`, `:7`).

## Cuándo se invoca
- Tipo `implementacion` que no cabe en línea y no es de complejidad ≥4 ni de >5 archivos (`~/.claude/orchestrator/policy.md:30`).
- `ESCALAR` de `rapido` (`~/.claude/orchestrator/policy.md:17`).
- Cada tramo tras un `OK` de `arquitecto` (`~/.claude/orchestrator/policy.md:21`).
- Re-brief tras `RECHAZADO` con `Causa: implementación` o tras gate determinista en rojo (`~/.claude/orchestrator/policy.md:20`, `:44`).

Ver [../routing.md](../routing.md).

## Input
El brief: objetivo, archivos permitidos, criterios de aceptación, comando de verificación, límites y ruta del plan si existe (`~/.claude/orchestrator/policy.md:39`). En un re-brief, también los hallazgos del `verificador`. Ve CLAUDE.md de usuario y de proyecto, y con ellos la política y la config de proyecto. NO ve el historial del chat. Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Texto de ≤8 líneas (`~/.claude/agents/implementador.md:14-19`):
- `ESTADO: OK | ESCALAR: <motivo> | AMPLIAR: <archivos+motivo> | PENDIENTE_APROBACION: <acción>`
- `Archivos:`
- `Verificación: <comando> → <resultado>`
- `Pendientes:`
- Detalle largo en `.claude/work/<tarea>.md`.

Schema: [../contracts/implementador-output.schema.json](../contracts/implementador-output.schema.json).

## Tools y permisos
Todas las tools salvo `Agent` (`~/.claude/agents/implementador.md:7`).

**Destructivo posible:** edita, crea y puede borrar archivos con `Write`, `Edit` y `Bash`. Lo mitigan los permisos `ask`/`deny` de `~/.claude/settings.json`, los `Edit(<ruta>)` de la config de proyecto en `.claude/settings.json` del repo, y los hooks `block-force-push` y `guard-secrets`.

## Por qué este modelo
Sonnet es el modelo de código equilibrado; effort high porque la prioridad es calidad sobre coste. Ver [../decisions/0002-modelo-por-rol.md](../decisions/0002-modelo-por-rol.md).

## Modos de fallo
| Síntoma | Causa probable | Respuesta del orquestador |
|---|---|---|
| `ESCALAR` | Hace falta diseño | Replan con `arquitecto`, o AskUserQuestion si ya se usó (`~/.claude/orchestrator/policy.md:19`) |
| `AMPLIAR` | Brief incompleto | Re-brief si sigue en alcance; si no, preguntar (`~/.claude/orchestrator/policy.md:16`) |
| Gate determinista en rojo | Bug o test roto | Re-brief al mismo ejecutor; cuenta como ciclo (`~/.claude/orchestrator/policy.md:44`) |
| `RECHAZADO` del `verificador` por segunda vez | Calidad insuficiente | Parar y reportar (`~/.claude/orchestrator/policy.md:34`) |
| Llega a 40 turnos | Tarea mal acotada | `[VERIFICAR: comportamiento al alcanzar maxTurns]` |

## Ejemplo
Ilustrativo.

Input (brief): "Objetivo: validar formato de email en registro. Archivos: `src/routes/auth.js`, `src/validators/user.js`, `test/auth.test.js`. Criterio: 400 con email inválido. Verificación: `pnpm test`."
Output:
```
ESTADO: OK
Archivos: src/validators/user.js, src/routes/auth.js, test/auth.test.js
Verificación: pnpm test → 42 passed
Pendientes: ninguno
```

## Código
- `~/.claude/agents/implementador.md`
- `~/.claude/orchestrator/policy.md:16-21`, `:30`, `:39-41`, `:44`
