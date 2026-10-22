---
description: Activa el orquestador restringido en el proyecto actual (crea .claude/orchestrator.md y permisos)
---
En el repo actual:
1. Si no existe, crea `.claude/orchestrator.md` copiando `~/.claude/orchestrator/project-template.md`. Rellena test/lint/build y rutas sensibles detectando el stack (package.json, pyproject, Makefile, carpetas migrations/infra/auth, .env*). Pregunta solo lo que no puedas deducir.
2. Importa `.claude/orchestrator.md` desde el CLAUDE.md del proyecto (créalo en la raíz si falta). La ruta del `@import` es relativa al CLAUDE.md que la contiene: raíz → `@.claude/orchestrator.md`; si el CLAUDE.md está en `.claude/CLAUDE.md` → `@orchestrator.md`. No dupliques si ya está.
3. En `.claude/settings.json` del proyecto, añade a `permissions.ask` una entrada `Edit(<ruta sensible>)` por cada ruta sensible (Edit cubre también Write; no uses `Write(...)`: Claude Code no la consulta), y a `permissions.deny` `Read(./.env*)` si hay .env. Fusiona con lo existente, no sobrescribas. No añadas reglas `allow`.
4. Añade `.claude/work/` al `.gitignore` del repo (créalo si falta; no dupliques). Ahí escriben los workers planes y reportes largos.
5. No crees ni modifiques `.claude/agents/` del proyecto (pisaría los workers globales). Si ya existe alguno con nombre de worker, avísalo.
6. Muestra diff resumido. No hagas commit.
