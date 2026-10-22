# Ejemplo: búsqueda amplia y cambio pequeño en línea

Recorrido de una pregunta que exige buscar en muchos archivos y acaba en un cambio de una línea hecho por el router. **Ilustrativo:** construido a partir de la política. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

Petición: "¿Dónde se configura el rate limit de carritos y súbelo de 20 a 30 por hora?"

| # | Actor | Qué pasa | Regla |
|---|---|---|---|
| 1 | Router (opus) | Clasifica en línea. La primera parte es `busqueda` con ubicación desconocida | `~/.claude/orchestrator/policy.md:10` |
| 2 | Router | Tabla B: búsqueda que no es de ≤3 archivos conocidos → `Explore`. Motivo: aislamiento de contexto | `policy.md:7`, `:27` |
| 3 | `Explore` (haiku, low) | Sin CLAUDE.md, solo lectura, excluyendo `.env*`. Devuelve `Conclusión` y `Evidencia: backend/src/middleware/rateLimit.ts:8 — max: 20` | `~/.claude/agents/Explore.md:8-16` |
| 4 | Router | Tabla A, regla 7: OK de `Explore` → sigue en línea con el resultado | `policy.md:21` |
| 5 | Router | La segunda parte es `implementacion`: 1 archivo, complejidad 1, riesgo bajo → en línea | `policy.md:30` |
| 6 | Router | Edita la línea. Gate determinista: test y lint verdes | `policy.md:44` |
| 7 | Router | Riesgo bajo y 1 archivo: sin `verificador` | `policy.md:45` |
| 8 | Router → usuario | Consolidación final: gates verdes, 1 archivo, sin pendientes, ruta (haiku buscó → opus editó en línea) | `policy.md:53` |

Si `Explore` hubiera necesitado leer `.env` para responder, habría devuelto `PENDIENTE_APROBACION` (`~/.claude/agents/Explore.md:12`), y el hook `guard-secrets` habría pedido confirmación ante cualquier `cat .env` (`~/.claude/hooks/guard-secrets`).
