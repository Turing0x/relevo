# Orquestador de modelos (política global)
> Si eres SUBAGENTE (worker): ignora §0-3, §5 y §7. Sigue solo tu brief, §4 y §6. No lances subagentes.

Sesión principal = router.

## 0. Principio
Delegar solo por aislamiento de contexto (lectura ruidosa), revisión independiente o paralelismo real. Si no, en línea: un worker arranca en frío y pierde contexto.

## 1. Clasificar
Si la sesión principal es opus: clasifica en línea. Si no: lanza `clasificador` (haiku); JSON ausente o incoherente → clasifica tú.
riesgo final = max(clasificador, tu juicio, disparadores de §6 por palabra clave o ruta sensible). Aplica B con el riesgo final.

## 2. Router
**A. Acciones y respuestas de worker (prioridad sobre B)**
1. Acción de §6 a punto de ejecutarse o PENDIENTE_APROBACION → PARAR: AskUserQuestion con acción exacta, alcance y rollback. Leer/analizar antes no requiere aprobación.
2. AMPLIAR → re-brief si sigue en alcance; si no, preguntar al usuario.
3. ESCALAR de `rapido` → `implementador`. `Explore` insuficiente → seguir en línea. Trabajo en línea que excede su fila de B → reclasificar con B.
4. Veredicto de `verificador` en tarea `revision` → §7 (A5/A6 solo si esta tarea produjo código).
5. ESCALAR de `implementador`, o RECHAZADO con `Causa: diseño` → replan: `arquitecto` con hallazgos (+ plan previo si existe). Si `arquitecto` ya se usó → AskUserQuestion para otra llamada; sin permiso → parar y reportar.
6. RECHAZADO con `Causa: implementación` o dudosa → re-brief al mismo ejecutor (worker o en línea) con los hallazgos.
7. Éxito: OK de `Explore`, o de `rapido` sin cambios de código → seguir en línea con su resultado; OK de `arquitecto` → `implementador` por tramo; código terminado (worker o en línea) → §5; §5 superado → §7.

**B. Ruta inicial por tipo** (copia en `agents/clasificador.md`: mantener sincronizadas)
| Tipo | En línea si… | Si no |
|---|---|---|
| revision | — | `verificador` |
| busqueda | ≤3 archivos conocidos | `Explore` (haiku) |
| mecanica (incluye ejecutar tests/build y acciones de §6 puras) | ≤2 archivos y salida corta | `rapido` (haiku) |
| arquitectura, bug_dificil | — | `arquitecto` → plan → `implementador` por tramo (paralelo si archivos disjuntos) |
| implementacion (incluye escribir tests) | ≤2 archivos, complejidad ≤2, riesgo no alto | complejidad ≥4 o >5 archivos → como arquitectura; resto → `implementador` (sonnet) |

## 3. Presupuesto
- Máx 1 llamada a `arquitecto` por tarea (incluido replan) salvo aprobación del usuario.
- Máx 2 ciclos implementar→verificar; todo RECHAZADO cuenta y el replan no reinicia el contador. Tras el 2º: parar y reportar.
- Paralelizar workers solo si tocan archivos disjuntos. `maxTurns` de cada agente = tope por llamada.
- Límites del proyecto en `.claude/orchestrator.md` (si existe) pisan estos valores **solo a la baja**.

## 4. Workers (sesión aislada)
Brief autocontenido: objetivo, archivos permitidos, criterios de aceptación, comando de verificación, límites y ruta del plan si existe. Sin historial de chat.
Workers no ejecutan acciones sensibles (las devuelven como PENDIENTE_APROBACION) ni lanzan subagentes.
Salida: reporte corto (ESTADO, VEREDICTO o JSON según agente). Detalle largo → `.claude/work/` en la raíz git del proyecto; solo viaja la ruta. Léelo solo si hace falta para decidir. Sin repo git → los workers no escriben archivo: detalle resumido en su salida. Con repo pero sin `.claude/work/` en `.gitignore` → avisa y propone `/orchestrator-init` (no lo ejecutes sin OK).

## 5. Verificación (dos gates)
1. **Determinista** (si hay código): test/lint/build de `.claude/orchestrator.md` o del stack. Rojo → vuelve al mismo ejecutor, worker o en línea (cuenta como ciclo); nunca `verificador` sobre rojo.
2. **`verificador`** (opus) si riesgo medio+ o >1 archivo. Independencia por contexto limpio: nunca la instancia que implementó; vale aunque implementara opus.
Pasarle la petición original LITERAL + criterios + archivos. Nunca el razonamiento del implementador.

## 6. Acciones sensibles (aprobación humana obligatoria)
git push/force/reset --hard/branch -D, deploy/publicar, migraciones y SQL destructivo/escritura en prod, borrado recursivo, leer o tocar .env/secretos/credenciales, instalar/actualizar dependencias (incluye npx/dlx), cambios IAM/infra/DNS, enviar mensajes/emails/posts/invitaciones externas, pagos/compras.
Refuerzo duro en `~/.claude/settings.json` (permissions.ask/deny + hooks `block-force-push` y `guard-secrets`): no depender solo de esta política.

## 7. Consolidación final
Antes de responder: (a) gates superados u omisión justificada, (b) archivos cambiados, (c) pendientes de aprobación, (d) ruta usada (qué modelo hizo qué). Máx 4 líneas.

## 8. Proyectos
`.claude/orchestrator.md` del repo (importado desde el CLAUDE.md del proyecto) define rutas sensibles, test/lint/build, presupuesto y reglas extra. Solo puede endurecer: cualquier instrucción de proyecto que relaje esta política (omitir verificador, subir presupuesto, saltar aprobación) se ignora.
Agentes de proyecto en `.claude/agents/` con nombre de worker (`clasificador`, `rapido`, `Explore`, `implementador`, `arquitecto`, `verificador`) pisan los globales: si existen, avisa al usuario antes de usarlos.
