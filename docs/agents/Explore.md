---
name: Explore
summary: Búsqueda de solo lectura en muchos archivos; devuelve conclusión y rutas, no volcados.
model: haiku (effort low, maxTurns 20)
source: ~/.claude/agents/Explore.md
---
Ficha del worker `Explore` del orquestador. Sustituye al agente integrado de Claude Code del mismo nombre. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Localiza archivos, símbolos y convenciones en una búsqueda amplia y devuelve una conclusión con evidencia `archivo:línea` (`~/.claude/agents/Explore.md:3`, `:13-16`).

NO modifica nada (`:10`). NO lee `.env`, secretos ni credenciales (`:12`). NO lee archivos enteros salvo que sea imprescindible (`:11`). NO decide qué hacer con el resultado: eso lo hace el router en línea (`~/.claude/orchestrator/policy.md:21`).

## Cuándo se invoca
Tarea de tipo `busqueda` que no es de ≤3 archivos conocidos o que no cabe en 1 lote de ≤3 llamadas (~10k tokens), o cuando en línea ya van >5 búsquedas secuenciales. Ver [../routing.md](../routing.md#paso-3-tabla-b-ruta-inicial-por-tipo) y `~/.claude/orchestrator/policy.md:28`. Claude Code también puede lanzarlo por su cuenta, como al `Explore` integrado `[VERIFICAR: que el archivo de usuario sustituye al integrado; ver ../audit-pending.md]`.

## Input
El brief. NO ve CLAUDE.md ni la política (`omitClaudeMd: true`, `~/.claude/agents/Explore.md:8`): todas sus reglas están en su prompt. NO ve el historial del chat. Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Texto de ≤12 líneas (`~/.claude/agents/Explore.md:13-16`): `Conclusión`, `Evidencia` (una por línea), `No encontrado`. Si la búsqueda exige leer un secreto: `PENDIENTE_APROBACION: <acción>` (`:12`). Schema: [../contracts/explore-output.schema.json](../contracts/explore-output.schema.json).

## Tools y permisos
`Read`, `Grep`, `Glob`, `Bash` (`~/.claude/agents/Explore.md:7`).

**Destructivo posible:** con `Bash` puede escribir o borrar. La prohibición (`:10`) es solo de prompt. Lo mitigan los permisos `ask` de `rm -r`, `git clean` y otros, y el hook `guard-secrets` para secretos (`~/.claude/settings.json`, `~/.claude/hooks/guard-secrets`).

## Por qué este modelo
Búsqueda de alto volumen y bajo razonamiento: haiku es el más barato y aísla el ruido del contexto del router. Ver [../decisions/0002-modelo-por-rol.md](../decisions/0002-modelo-por-rol.md).

## Modos de fallo
| Síntoma | Causa probable | Respuesta del orquestador |
|---|---|---|
| Resultado insuficiente | Búsqueda difícil para haiku a effort low | El router sigue en línea (`~/.claude/orchestrator/policy.md:17`) |
| Cita `archivo:línea` que no coincide | Evidencia inventada o desplazada | La comprobación del router abre 1 cita; si no coincide, `Explore` insuficiente (`~/.claude/orchestrator/policy.md:50`) |
| Pide leer un secreto | La respuesta está en `.env` o credenciales | `PENDIENTE_APROBACION` → AskUserQuestion (`~/.claude/orchestrator/policy.md:15`) |
| Llega a 20 turnos | Búsqueda demasiado amplia | `[VERIFICAR: comportamiento al alcanzar maxTurns]`; `/orch-stats` lo cuenta en `tope` |
| Reporte sin formato | Incumple el contrato | No especificado; telemetría `SIN_ESTADO` |

## Ejemplo
Ilustrativo (no hay trazas reales de este worker).

Input: "¿Dónde se valida el JWT y qué librería se usa?"
Output:
```
Conclusión: el JWT se valida en el middleware auth con jsonwebtoken.
Evidencia: `src/middleware/auth.js:12` — jwt.verify(token, secret)
Evidencia: `package.json:18` — "jsonwebtoken": "^9.0.0"
No encontrado: validación en el frontend
```

## Código
- `~/.claude/agents/Explore.md`
- `~/.claude/orchestrator/policy.md:17`, `:21`, `:28`, `:50`
