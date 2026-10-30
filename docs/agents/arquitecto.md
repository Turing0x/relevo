---
name: arquitecto
summary: Diagnostica bugs difíciles o diseña cambios multi-módulo y escribe un plan en tramos.
model: opus (effort xhigh, maxTurns 45)
source: ~/.claude/agents/arquitecto.md
---
Ficha del worker `arquitecto` del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

## Rol
Entrega diagnóstico o diseño, no código masivo (`~/.claude/agents/arquitecto.md:9`):
- Bug: reproduce, aísla la causa raíz con evidencia `archivo:línea` y propone un fix mínimo (`:10`).
- Diseño: máximo 3 opciones, una recomendación, riesgos y un plan en tramos para `implementador` con archivos, criterios y verificación por tramo (`:11`).
- Replan: corrige la causa, actualiza el mismo archivo de plan y marca qué tramos cambian (`:12`).

NO edita código salvo que el brief lo pida; solo escribe `.claude/work/plan-<tarea>.md` (`:13`). NO ejecuta acciones sensibles (`:13`). NO lanza subagentes (`disallowedTools: Agent`, `:7`).

## Cuándo se invoca
- Tipo `arquitectura` o `bug_dificil` (`~/.claude/orchestrator/policy.md:30`).
- Tipo `implementacion` con complejidad ≥4 o >5 archivos (`~/.claude/orchestrator/policy.md:31`).
- Replan tras `ESCALAR` de `implementador` o `RECHAZADO` con `Causa: diseño` (`~/.claude/orchestrator/policy.md:19`).

Máximo 1 llamada por tarea, incluido el replan, salvo aprobación del usuario (`~/.claude/orchestrator/policy.md:35`). Ver [../routing.md](../routing.md).

## Input
El brief; en un replan, también los hallazgos y el plan previo si existe (`~/.claude/orchestrator/policy.md:19`). Ve CLAUDE.md de usuario y de proyecto. NO ve el historial del chat. Schema: [../contracts/brief.schema.json](../contracts/brief.schema.json).

## Output
Texto de ≤8 líneas (`~/.claude/agents/arquitecto.md:14-19`): `ESTADO: OK | PENDIENTE_APROBACION: <acción>`, `Plan:` (ruta), `Conclusión:`, `Tramos:`, `Riesgos:`. El contenido completo va en el archivo de plan. No tiene `ESCALAR` ni `AMPLIAR` en su contrato. Schema: [../contracts/arquitecto-output.schema.json](../contracts/arquitecto-output.schema.json).

## Tools y permisos
Todas las tools salvo `Agent` (`~/.claude/agents/arquitecto.md:7`).

**Destructivo posible:** tiene `Write`, `Edit` y `Bash`. La limitación a un solo archivo es solo de prompt (`:13`). Lo mitigan los permisos y hooks globales.

## Por qué este modelo
Razonamiento más fuerte disponible en la escalera, a effort xhigh; es el más caro, por eso tiene presupuesto de 1 llamada. Ver [../decisions/0002-modelo-por-rol.md](../decisions/0002-modelo-por-rol.md) y [../decisions/0007-presupuesto.md](../decisions/0007-presupuesto.md).

## Modos de fallo
| Síntoma | Causa probable | Respuesta del orquestador |
|---|---|---|
| No puede entregar plan | Información insuficiente | No especificado: su contrato no tiene `ESCALAR` |
| Hace falta un segundo replan | El primer plan falló | AskUserQuestion; sin permiso, parar y reportar (`~/.claude/orchestrator/policy.md:19`) |
| Sin repo git | No hay `.claude/work/` | Detalle resumido en la salida, sin archivo (`~/.claude/orchestrator/policy.md:44`) |
| Llega a 45 turnos | Problema muy amplio | Vuelve al router con una nota de límite de turnos y sin `ESTADO`; no se dispara `SubagentStop` y no queda línea en `log.jsonl` (E2E con Claude Code 2.1.312, [../audit-pending.md](../audit-pending.md) #2) |

## Ejemplo
Ilustrativo.

Output:
```
ESTADO: OK
Plan: .claude/work/plan-pagos-idempotencia.md
Conclusión: añadir clave de idempotencia por pedido y comprobarla antes de cobrar.
Tramos: 2 — modelo+migración, servicio de cobro
Riesgos: la migración toca la colección de pedidos (acción sensible).
```

## Código
- `~/.claude/agents/arquitecto.md`
- `~/.claude/orchestrator/policy.md:19`, `:21`, `:30-31`, `:35`
