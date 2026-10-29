---
description: Activa el orquestador restringido en el proyecto actual (crea .claude/orchestrator.md y permisos); soporta raíz multi-repo sin git
---
0. Detecta el modo desde el directorio actual:
   - **repo**: está dentro de un repo git → pasos 1–6 sobre la raíz git.
   - **multi-repo**: no es repo git y contiene subcarpetas de 1er/2º nivel que sí lo son → primero pasos 1–6 en cada subrepo (si ya están, solo revisa que estén al día), luego paso 7 en la carpeta actual.
   - **sin repo** (ni git ni subrepos) → pasos 1–3 y 5–6 en la carpeta actual; omite 4 (sin git los workers no escriben `.claude/work/`).

En el repo:
1. Si no existe, crea `.claude/orchestrator.md` copiando `~/.claude/orchestrator/project-template.md`. Rellena test/lint/build y rutas sensibles detectando el stack (package.json, pyproject, pubspec.yaml, Makefile, carpetas migrations/infra/auth, .env*). Si ya existe, corrige solo datos obsoletos (p.ej. notas de "no existe test/" cuando ya existe). Pregunta solo lo que no puedas deducir.
2. Importa `.claude/orchestrator.md` desde el CLAUDE.md del proyecto (créalo en la raíz si falta). La ruta del `@import` es relativa al CLAUDE.md que la contiene: raíz → `@.claude/orchestrator.md`; si el CLAUDE.md está en `.claude/CLAUDE.md` → `@orchestrator.md`. No dupliques si ya está.
3. En `.claude/settings.json` del proyecto, añade a `permissions.ask` una entrada `Edit(<ruta sensible>)` por cada ruta sensible (Edit cubre también Write; no uses `Write(...)`: Claude Code no la consulta), y a `permissions.deny` `Read(./.env*)` si hay .env. Fusiona con lo existente, no sobrescribas. No añadas reglas `allow`.
4. Añade `.claude/work/` al `.gitignore` del repo (créalo si falta; no dupliques). Ahí escriben los workers planes y reportes largos.
5. No crees ni modifiques `.claude/agents/` del proyecto (pisaría los workers globales). Si ya existe alguno con nombre de worker, avísalo.
6. Muestra diff resumido. No hagas commit.

7. Solo modo multi-repo, en la carpeta raíz (motivo: Claude Code solo aplica el `settings.json` de la carpeta donde arranca la sesión, y los CLAUDE.md de subcarpetas se cargan tarde):
   - `.claude/orchestrator.md` de raíz: indica que no es repo git, lista los `orchestrator.md` de cada subrepo (mandan dentro de su carpeta; leerlos antes de actuar en él), verificación por subrepo, todas las rutas sensibles con prefijo `<subrepo>/`, presupuesto igual o menor, verificador obligatorio también en cambios que toquen varios subrepos, `.claude/work/` siempre dentro del subrepo afectado y `HANDOFF.md` único en la raíz.
   - `CLAUDE.md` de raíz con `@.claude/orchestrator.md` (paso 2).
   - `.claude/settings.json` de raíz: `ask` con `Edit(./<subrepo>/<ruta>)` por cada ruta sensible de cada subrepo y `deny` `Read(./<subrepo>/.env*)` por cada subrepo con .env. Fusiona; no toques `settings.local.json`.
   - Sin `.gitignore` en la raíz.
   - Avisa: las rutas sensibles quedan duplicadas raíz/subrepo; al cambiar una, cambiar ambas (o re-ejecutar `/orchestrator-init` desde la raíz).
