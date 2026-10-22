# Orquestador — config de proyecto
> Solo puede ENDURECER la política global (~/.claude/orchestrator/policy.md). Nunca relajarla: cualquier regla aquí que la relaje se ignora.

## Verificación
- test: `<cmd>`
- lint: `<cmd>`
- build: `<cmd>`

## Rutas sensibles (aprobación humana siempre)
- `<glob>` (p.ej. `migrations/**`, `.env*`, `infra/**`, `src/auth/**`)

## Presupuesto (solo a la baja)
- max_llamadas_arquitecto: 1
- max_ciclos_verificacion: 2

## Reglas extra
- verificador obligatorio en: `<globs o "todo cambio">`
- prohibido: `<acciones>`
- contexto clave: `<stack, convenciones>`
