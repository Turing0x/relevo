# 0009 — Riesgo declarado y re-verificación limitada

ADR del orquestador. Términos en [../GLOSSARY.md](../GLOSSARY.md). Rutas absolutas desde `~/.claude/` salvo indicación.

## Contexto
El riesgo se decidía solo antes de actuar (`clasificador` + juicio del router + palabras clave de §6), con una lista de palabras clave sin numerar que vivía solo en `clasificador`. El diff real podía tocar más de lo previsto sin que nada lo declarara. El 2º ciclo implementar→verificar repetía una revisión completa, y un hallazgo nuevo podía gastar el último ciclo aunque el defecto ya existiera antes del cambio. El brief tenía "archivos permitidos" sin formato, y los prompts bloqueantes podían llegar resumidos al usuario. Comparativa de origen: `docs/Gentle AI vs relevo qué aprender.md` del repo (fase 1, ideas 2-10).

## Decisión
Solo se añaden reglas; ninguna se relaja.
- **Lista de alto riesgo numerada** (§6bis, `~/.claude/orchestrator/policy.md:53-60`): 1 datos/irreversible, 2 seguridad, 3 contratos consumidos por otros, 4 concurrencia, 5 entrega/entorno/dependencias, 6 ningún test detectaría una regresión. 1-5 → riesgo alto; 6 → mínimo medio. `clasificador` lleva la misma lista con los mismos números (`~/.claude/agents/clasificador.md:23-29`) y conserva todas sus palabras clave anteriores.
- **Línea de riesgo obligatoria**: `implementador`, `rapido` y el trabajo en línea con cambios cierran con `Riesgo: <N>[,<N>] (<motivo>) | ninguno`; antes de `ninguno` se comprueba el código compartido (= 3). Entra en el `max()` del riesgo final (`policy.md:11`); si falta, riesgo mínimo medio.
- **Presupuesto de evidencia en la fila `busqueda`**: en línea solo si son ≤3 archivos conocidos **y** cabe en 1 lote de ≤3 llamadas (~10k tokens); >5 búsquedas secuenciales en línea → `Explore` (`policy.md:27`). Complementa el número de archivos, no lo sustituye.
- **Comprobación del router** (`policy.md:47`): antes de §7 re-ejecuta 1 comando reportado y abre 1 cita `archivo:línea` de `Explore`.
- **Severidad con base y precision gate** (`~/.claude/agents/verificador.md:13-14`): el `verificador` recibe `base_commit`; bloqueante = causado por el cambio y no reproducible en la base; solo hallazgos defendibles con evidencia, sin estilo. Siempre bloqueante: criterio de aceptación incumplido, regresión introducida por el fix de un ciclo anterior, opción explícita ignorada, salida no pedida cambiada, secretos o acción sensible no aprobada.
- **Recheck** (`policy.md:34`, `verificador.md:15`): tras `RECHAZADO` con `Causa: implementación` o dudosa, el 2º ciclo revisa solo `recheck_findings`; un hallazgo nuevo es advertencia, no consume ni abre ciclo y llega a §7 como pendiente. Tras un replan la revisión vuelve a ser completa.
- **Superficie permitida** (`policy.md:39`, [../contracts/brief.schema.json](../contracts/brief.schema.json)): rutas o globs estrechos, nunca `.` ni absolutas; si no se puede derivar, AskUserQuestion con candidatos. El brief añade `base_commit`, `modo` y `recheck_findings[]`.
- **Paralelismo por unidad de comportamiento** (`policy.md:35`): además de archivos disjuntos, unidades independientes de ~100+ líneas; código, tests y docs de una unidad van juntos.
- **Prompts bloqueantes sin pérdida** (`policy.md:15-16`): al relayar `PENDIENTE_APROBACION` o `AMPLIAR` se conservan todas las opciones literales; sin UI interactiva, se muestra completo y se para.

## Por qué
- El riesgo declarado sobre el diff real es una comprobación posterior que el riesgo previo no da; si sube, §5 lanza el `verificador`.
- Numerar la lista permite un test que mantiene sincronizadas las dos copias (`tests/test_repo_consistency.py`, `PolicySyncTests`).
- Recheck y severidad con base abaratan el 2º ciclo de opus sin quitar ninguna revisión: el límite de 2 ciclos sigue igual y los defectos preexistentes no consumen presupuesto.

## Alternativas
- Verificador solo en alto riesgo con nombre (gentle-ai). Descartada: deja sin revisar el riesgo medio ([0004-verificacion-dos-gates.md](0004-verificacion-dos-gates.md)).
- Sustituir el número de archivos por el presupuesto de evidencia. Descartada: la tabla B es la base del routing por coste ([0003-delegar-por-motivo.md](0003-delegar-por-motivo.md)).
- Recheck también tras replan. Descartada: el código cambia de enfoque y la revisión limitada perdería defectos nuevos.

## Consecuencias
- Un hallazgo nuevo en recheck no bloquea salvo que sea de los "siempre bloqueante" (incluida una regresión causada por el propio fix; el gate determinista sigue aplicando); queda visible en la consolidación final para que decida el usuario.
- Contratos de salida de `implementador` y `rapido` con un campo `riesgo` obligatorio; `verificador` con severidad `bloqueante|advertencia` y campo `recheck`.
- Sigue sin enforcement: la línea de riesgo, el recheck y la comprobación del router son texto de política ([0001-politica-con-refuerzo-duro.md](0001-politica-con-refuerzo-duro.md)). Solo la sincronización de la lista y de la fila `busqueda` se comprueba en CI.
- `[VERIFICAR]` qué hace el `verificador` si el brief llega sin `base_commit` (ver [../failure-modes.md](../failure-modes.md)).
