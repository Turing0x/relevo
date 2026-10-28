# Ejemplo: implementación con un rechazo del verificador

Recorrido de punta a punta de una implementación de 3 archivos con un `RECHAZADO` y su corrección. **Ilustrativo:** está construido a partir de la política; no hay traza completa guardada. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/`.

Petición: "En 4CaminosStore, añade límite de 5 unidades por producto al carrito."
Contexto: `~/LocalProjects/4CaminosStore/.claude/orchestrator.md` existe, con verificación por `pnpm --dir backend test|lint|build` y "verificador obligatorio en: pedidos/stock".

| # | Actor | Qué pasa | Regla |
|---|---|---|---|
| 1 | Router (opus) | Clasifica en línea: `implementacion`, riesgo medio (pedidos/stock), complejidad 3, 3 archivos | `~/.claude/orchestrator/policy.md:10-11` |
| 2 | Router | Tabla B: no cabe en línea (3 archivos > 2) y no llega a `arquitecto` (complejidad <4, ≤5 archivos) → `implementador` | `policy.md:31` |
| 3 | Router → `implementador` | Brief: objetivo, archivos `backend/src/cart/*.ts`, criterio "422 si cantidad > 5", verificación `pnpm --dir backend test` | `policy.md:42` |
| 4 | `implementador` (sonnet, high) | `ESTADO: OK`, 3 archivos, `pnpm --dir backend test → passed` | `~/.claude/agents/implementador.md:15-20` |
| 5 | Hook `orch-telemetry` | Registra `{"agent":"implementador","status":"OK",...}` | `~/.claude/hooks/orch-telemetry` |
| 6 | Router | Gate determinista: test, lint y build del backend → verde | `policy.md:47` |
| 7 | Router → `verificador` | Riesgo medio y >1 archivo. Recibe la petición literal, los criterios y los archivos; no el razonamiento | `policy.md:48-49` |
| 8 | `verificador` (opus, high) | `VEREDICTO: RECHAZADO`, `Causa: implementación`: el límite no se aplica al actualizar una línea existente del carrito | `~/.claude/agents/verificador.md:17-19` |
| 9 | Router | Tabla A, regla 6: re-brief al mismo ejecutor con los hallazgos. Ciclo 1 de 2 | `policy.md:20`, `:36` |
| 10 | `implementador` | `ESTADO: OK` con la corrección y un test nuevo | — |
| 11 | Router | Gate determinista verde → `verificador` con contexto limpio → `APROBADO` | `policy.md:47-48` |
| 12 | Router → usuario | Consolidación final en ≤4 líneas: gates superados, archivos, pendientes (ninguno), ruta (opus clasificó → sonnet implementó ×2 → opus verificó ×2) | `policy.md:66` |

Si el paso 8 hubiera sido `Causa: diseño`, la regla 5 de la tabla A habría lanzado un replan con `arquitecto` (`policy.md:19`). Un segundo `RECHAZADO` en el paso 11 habría parado la tarea (`policy.md:36`).

Dato real de contexto: en `~/.claude/orchestrator/log.jsonl`, 1 de las 4 llamadas reales a `verificador` (2026-10-22) fue `RECHAZADO`.
