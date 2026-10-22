---
name: rapido
summary: Ejecuta tareas mecánicas exactamente como se piden, sin rediseñar.
model: haiku (effort low, maxTurns 15)
source: ~/.claude/agents/rapido.md
---
Ficha del worker `rapido` del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Hace tareas mecánicas en varios archivos: renombrar, formatear, cambios de 1-2 líneas, boilerplate, listar dependencias, ejecutar tests o build con salida larga (`~/.claude/agents/rapido.md:3`, `:9`; `~/.claude/orchestrator/policy.md:28`).

NO rediseña (`:9`). NO toca varios módulos ni toma decisiones de diseño: devuelve `ESCALAR` (`:10`). NO ejecuta acciones sensibles: devuelve `PENDIENTE_APROBACION` (`:11`).

## Cuándo se invoca
Tarea de tipo `mecanica` que no es de ≤2 archivos con salida corta. Ver [../routing.md](../routing.md#paso-3-tabla-b-ruta-inicial-por-tipo) y `~/.claude/orchestrator/policy.md:28`.

## Input
El brief. Ve CLAUDE.md de usuario y de proyecto (no declara `omitClaudeMd`), y por tanto la política con la instrucción para workers de `~/.claude/orchestrator/policy.md:2`. NO ve el historial del chat (`~/.claude/orchestrator/policy.md:39`). Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Texto de ≤8 líneas (`~/.claude/agents/rapido.md:12-15`):
- `ESTADO: OK | ESCALAR | PENDIENTE_APROBACION: <acción>`
- `Resultado:` en búsqueda, `archivo:línea` más ≤1 línea; en cambio, rutas tocadas.
- Detalle largo en `.claude/work/<tarea>.md`; solo la ruta en la salida.

No tiene `AMPLIAR` en su contrato. Schema: [../contracts/rapido-output.schema.json](../contracts/rapido-output.schema.json).

## Tools y permisos
`Read`, `Grep`, `Glob`, `Bash`, `Edit` (`~/.claude/agents/rapido.md:7`). Sin `Write` ni `Agent`.

**Destructivo posible:** modifica archivos con `Edit` y puede borrar con `Bash`. Lo mitigan los permisos `ask` (`rm -r`, `git clean`, `git reset --hard`…) y los hooks `block-force-push` y `guard-secrets`.

## Por qué este modelo
Trabajo sin juicio de diseño; haiku a effort low es el más barato. Ver [../decisions/0002-modelo-por-rol.md](../decisions/0002-modelo-por-rol.md).

## Modos de fallo
| Síntoma | Causa probable | Respuesta del orquestador |
|---|---|---|
| `ESCALAR` | La tarea requiere diseño | Pasa a `implementador` (`~/.claude/orchestrator/policy.md:17`) |
| `PENDIENTE_APROBACION` | Acción sensible | AskUserQuestion (`~/.claude/orchestrator/policy.md:15`) |
| `OK` con cambios de código | — | Verificación en dos gates (`~/.claude/orchestrator/policy.md:21`) |
| Necesita archivos fuera del brief | No tiene `AMPLIAR` en su contrato | No especificado |
| Llega a 15 turnos | Tarea grande | `[VERIFICAR: comportamiento al alcanzar maxTurns]` |

## Ejemplo
Ilustrativo.

Input (brief): "Renombra `getUser` a `fetchUser` en `src/`. Verificación: `pnpm test`."
Output:
```
ESTADO: OK
Resultado: src/api/user.ts, src/pages/profile.tsx, src/hooks/useUser.ts
```

## Código
- `~/.claude/agents/rapido.md`
- `~/.claude/orchestrator/policy.md:17`, `:21`, `:28`
