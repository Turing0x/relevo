# Ejemplo: acción sensible con aprobación humana

Recorrido de una tarea que termina en una acción sensible (push y deploy), y de las capas que la frenan. **Ilustrativo:** construido a partir de la política, los permisos y los hooks. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

Petición: "Sube los cambios y despliega a producción."

| # | Actor | Qué pasa | Regla |
|---|---|---|---|
| 1 | Router (opus) | Clasifica: `mecanica` (acción sensible pura), riesgo alto | `~/.claude/orchestrator/policy.md:28`, `~/.claude/agents/clasificador.md:16` |
| 2 | Router | Tabla A, regla 1 (prioridad sobre B): acción de §6 a punto de ejecutarse → AskUserQuestion con la acción exacta (`git push origin main`, `vercel --prod`), el alcance y el rollback | `policy.md:15`, `:49` |
| 3 | Usuario | Aprueba el push y rechaza el deploy | — |
| 4 | Router | Ejecuta `git push origin main`. Claude Code vuelve a pedir permiso porque `Bash(git push:*)` está en `permissions.ask` | `~/.claude/settings.json` (`ask`) |
| 5 | Hook `block-force-push` | Comprueba el comando: no es force push → exit 0 | `~/.claude/hooks/block-force-push:40-44` |
| 6 | Router → usuario | Consolidación final: push hecho, deploy pendiente de aprobación | `policy.md:53` |

Variantes:

| Variante | Qué la frena | Fuente |
|---|---|---|
| `git push --force` | `permissions.deny` y el hook `block-force-push` (exit 2), aunque el usuario lo apruebe en el chat | `~/.claude/settings.json:7-10`, `~/.claude/hooks/block-force-push:43` |
| Un `implementador` intenta `pnpm add` | Su prompt le obliga a devolver `PENDIENTE_APROBACION`; además `Bash(pnpm add:*)` está en `ask` | `~/.claude/agents/implementador.md:12`, `~/.claude/settings.json` |
| `cat .env` para leer la URL de producción | Hook `guard-secrets` → `ask` | `~/.claude/hooks/guard-secrets` |
