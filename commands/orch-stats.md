---
description: Resume la telemetría del orquestador y propone ajustes del router
argument-hint: "[días, por defecto 30]"
---
Ejecuta `python3 ~/.claude/orchestrator/stats.py $ARGUMENTS` y muestra la tabla tal cual.
Después, máx 3 líneas de ajustes concretos solo si los datos los justifican (≥5 llamadas del agente), p.ej.:
- `tope` > 10 % de llamadas → subir `maxTurns` o partir tareas. Ojo: un worker que se detiene por `maxTurns` no deja línea (no hay `SubagentStop`), así que `tope` se queda corto.
- ESCALAR > 20 % en un agente → el router le asigna tareas demasiado difíciles.
- RECHAZADO > 30 % → revisar briefs o subir effort del implementador.
- SIN_ESTADO frecuente → el agente no cumple el contrato de salida.
No edites nada; propón y espera.
