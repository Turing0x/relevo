---
description: Diagnóstico de solo lectura de la instalación de relevo (pass/warn/fail + remedio)
argument-hint: "[--project DIR] [--json]"
---
Ejecuta `python3 ~/.claude/orchestrator/doctor.py $ARGUMENTS` y muestra la salida tal cual.
Después, máx 3 líneas: qué comprobación en `fail` atacar primero y por qué.
No ejecutes ningún remedio ni edites nada: cada remedio es una propuesta. Si el usuario pide aplicarlo y es una acción de §6 (p. ej. reinstalar o tocar `settings.json`), pide aprobación antes.
