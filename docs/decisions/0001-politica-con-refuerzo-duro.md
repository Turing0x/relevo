# 0001 — Política en lenguaje natural con refuerzo duro

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
El orquestador vive dentro de Claude Code, que carga CLAUDE.md en cada sesión y aplica permisos y hooks. La primera versión era una lista de reglas en CLAUDE.md (`~/.claude/backups/orch-1792227575/CLAUDE.md`).

## Decisión
- Las reglas de routing, presupuesto y verificación son texto en `~/.claude/orchestrator/policy.md`, importado desde `~/.claude/CLAUDE.md:6`.
- Lo crítico para la seguridad no depende solo del texto: "Refuerzo duro en `~/.claude/settings.json` (...): no depender solo de esta política" (`~/.claude/orchestrator/policy.md:50`).

## Alternativas
- Orquestador programado (Agent SDK u otro framework). `[VERIFICAR: no hay registro de que se evaluara]`.
- Solo texto, sin hooks. Descartada para seguridad (`policy.md:50`).

## Consecuencias
- Cero código que mantener para el routing. Cambiar una regla es editar texto.
- Presupuesto, gates y contratos dependen de que el modelo obedezca; no hay contador ni validador (ver [../ARCHITECTURE.md](../ARCHITECTURE.md#invariantes)).
- Force push y lectura explícita de secretos sí quedan impuestos por Claude Code.
