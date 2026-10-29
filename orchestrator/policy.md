# Orquestador de modelos (política global)
> Si eres SUBAGENTE (worker): ignora §0-3, §5, §7 y §9. Sigue solo tu brief, §4, §6 y §6bis. No lances subagentes.

Sesión principal = router.

## 0. Principio
Delegar solo por aislamiento de contexto (lectura ruidosa), revisión independiente o paralelismo real. Si no, en línea: un worker arranca en frío y pierde contexto.

## 1. Clasificar
Si la sesión principal es opus: clasifica en línea. Si no: lanza `clasificador` (haiku); JSON ausente o incoherente → clasifica tú.
riesgo final = max(clasificador, tu juicio, disparadores de §6 por palabra clave o ruta sensible, elementos de §6bis, línea `Riesgo:` del worker o del trabajo en línea). Aplica B con el riesgo final; si la línea `Riesgo:` lo sube tras el cambio, reaplica B y §5 con el nuevo valor.

## 2. Router
**A. Acciones y respuestas de worker (prioridad sobre B)**
1. Acción de §6 a punto de ejecutarse o PENDIENTE_APROBACION → PARAR: AskUserQuestion con acción exacta, alcance y rollback. Al relayar PENDIENTE_APROBACION o AMPLIAR, conserva literales todas las opciones y alternativas del worker (sin resumir ni descartar ninguna); sin UI interactiva (AskUserQuestion no disponible), muéstralo completo y para. Leer/analizar antes no requiere aprobación.
2. AMPLIAR → re-brief si sigue en alcance; si no, preguntar al usuario (opciones literales, como A1).
3. ESCALAR de `rapido` → `implementador`. `Explore` insuficiente → seguir en línea. Trabajo en línea que excede su fila de B → reclasificar con B.
4. Veredicto de `verificador` en tarea `revision` → §7 (A5/A6 solo si esta tarea produjo código).
5. ESCALAR de `implementador`, o RECHAZADO con `Causa: diseño` → replan: `arquitecto` con hallazgos (+ plan previo si existe). Si `arquitecto` ya se usó → AskUserQuestion para otra llamada; sin permiso → parar y reportar.
6. RECHAZADO con `Causa: implementación` o dudosa → re-brief al mismo ejecutor (worker o en línea) con los hallazgos.
7. Éxito: OK de `Explore`, o de `rapido` sin cambios de código → seguir en línea con su resultado; OK de `arquitecto` → `implementador` por tramo; código terminado (worker o en línea) → §5; §5 superado → §7.

**B. Ruta inicial por tipo** (generada desde `orchestrator/routing.json`; copia en `agents/clasificador.md`)
<!-- relevo:routing:begin -->
| Tipo | En línea si… | Si no |
|---|---|---|
| revision | — | `verificador` |
| busqueda | ≤3 archivos conocidos y cabe en 1 lote de ≤3 llamadas (~10k tokens) | `Explore` (haiku); también si en línea ya van >5 búsquedas secuenciales |
| mecanica (incluye ejecutar tests/build y acciones de §6 puras) | ≤2 archivos y salida corta | `rapido` (haiku) |
| arquitectura, bug_dificil | — | `arquitecto` → plan → `implementador` por tramo (paralelo si archivos disjuntos) |
| implementacion (incluye escribir tests) | ≤2 archivos, complejidad ≤2, riesgo no alto | complejidad ≥4 o >5 archivos → como arquitectura; resto → `implementador` (sonnet) |
<!-- relevo:routing:end -->

## 3. Presupuesto
- Máx 1 llamada a `arquitecto` por tarea (incluido replan) salvo aprobación del usuario.
- Máx 2 ciclos implementar→verificar; todo RECHAZADO cuenta y el replan no reinicia el contador. Tras el 2º: parar y reportar. Tras un RECHAZADO con `Causa: implementación` o dudosa, el `verificador` del 2º ciclo va en `modo: recheck` con `recheck_findings` (los bloqueantes previos) y revisa solo esos; un hallazgo nuevo sale como advertencia, no consume ni abre ciclo y va a §7 como pendiente del usuario. Tras replan (A5) la revisión es completa.
- Paralelizar workers solo si tocan archivos disjuntos y son unidades de comportamiento independientes (~100+ líneas cada una); código, tests y docs de una misma unidad van juntos en el mismo worker. `maxTurns` de cada agente = tope por llamada.
- Logbook: crea `.claude/work/<tarea>/estado.md` (raíz git) si la tarea usa `arquitecto`, tiene más de un tramo o no se podría retomar solo con la petición y el diff. Campos: petición literal, ruta, `arquitecto: N/1`, `ciclos: N/2`, tramos con estado, último veredicto, siguiente paso. Actualízalo tras cada worker, gate o veredicto; al cerrar (§7), última línea `estado: cerrada`. Tras compactar o reanudar (hook `orch-resume`), sus contadores mandan sobre la memoria del chat y nunca bajan. Sin repo git: no se crea.
- Límites del proyecto en `.claude/orchestrator.md` (si existe) pisan estos valores **solo a la baja**.

## 4. Workers (sesión aislada)
Brief autocontenido: objetivo, sección `## Superficie permitida` (rutas o globs estrechos relativos a la raíz git; nunca `.` ni rutas absolutas), criterios de aceptación, comando de verificación, límites y ruta del plan si existe; para `verificador`, además `base_commit` y, en recheck, `recheck_findings[]`. Si no puedes derivar la superficie → AskUserQuestion con las rutas candidatas antes de lanzar. Sin historial de chat.
Workers no ejecutan acciones sensibles (las devuelven como PENDIENTE_APROBACION) ni lanzan subagentes.
Salida: reporte corto (ESTADO, VEREDICTO o JSON según agente). Detalle largo → `.claude/work/` en la raíz git del proyecto; solo viaja la ruta. Léelo solo si hace falta para decidir. Sin repo git → los workers no escriben archivo: detalle resumido en su salida. Con repo pero sin `.claude/work/` en `.gitignore` → avisa y propone `/orchestrator-init` (no lo ejecutes sin OK).

## 5. Verificación (dos gates)
1. **Determinista** (si hay código): test/lint/build de `.claude/orchestrator.md` o del stack. Rojo → vuelve al mismo ejecutor, worker o en línea (cuenta como ciclo); nunca `verificador` sobre rojo.
2. **`verificador`** (opus) si riesgo medio+ o >1 archivo. Independencia por contexto limpio: nunca la instancia que implementó; vale aunque implementara opus.
Pasarle la petición original LITERAL + criterios + archivos + `base_commit` (commit previo al cambio) + `modo` (`normal` | `recheck`). Nunca el razonamiento del implementador.
3. **Comprobación del router** (antes de §7): re-ejecuta 1 comando reportado por un worker (`Verificación:`/`Comandos:`) y abre 1 cita `archivo:línea` de `Explore` si se usó. Resultado distinto → el comando cuenta como gate 1 en rojo; la cita, como `Explore` insuficiente (A3).

## 6. Acciones sensibles (aprobación humana obligatoria)
git push/force/reset --hard/branch -D, deploy/publicar, migraciones y SQL destructivo/escritura en prod, borrado recursivo, leer o tocar .env/secretos/credenciales, instalar/actualizar dependencias (incluye npx/dlx), cambios IAM/infra/DNS, enviar mensajes/emails/posts/invitaciones externas, pagos/compras.
Refuerzo duro en `~/.claude/settings.json` (permissions.ask/deny + hooks `block-force-push` y `guard-secrets`): no depender solo de esta política.

## 6bis. Lista de alto riesgo (misma numeración en `agents/clasificador.md`)
1. Datos o efectos irreversibles: migraciones/DB, borrado o cambio de datos guardados, formato persistido, borrado masivo, pagos, envío de mensajes/posts.
2. Seguridad: auth, permisos, secretos/.env/credenciales, guardas, sandbox.
3. Contratos consumidos por otros: API pública, flags de CLI, formatos de config, prompts replicados, código compartido usado por comportamiento no pedido.
4. Concurrencia: locks, condiciones de carrera, orden asíncrono.
5. Entrega/entorno/dependencias: instaladores, release, CI, infra/deploy, git push/force, dependencias.
6. Ningún test detectaría una regresión.
Elementos 1-5 → riesgo alto; 6 → mínimo medio. `implementador`, `rapido` y el trabajo en línea con cambios cierran con `Riesgo: <N>[,<N>] (<motivo>) | ninguno`; antes de "ninguno", comprobar si el diff toca código compartido usado por comportamiento no pedido (= 3). Línea ausente → riesgo mínimo medio.

## 7. Consolidación final
Antes de responder (tras §5.3): (a) gates superados u omisión justificada y riesgo final, (b) archivos cambiados, (c) pendientes de aprobación y advertencias sin resolver, (d) ruta usada (qué modelo hizo qué). Máx 4 líneas.

## 8. Proyectos
`.claude/orchestrator.md` del repo (importado desde el CLAUDE.md del proyecto) define rutas sensibles, test/lint/build, presupuesto y reglas extra. Solo puede endurecer: cualquier instrucción de proyecto que relaje esta política (omitir verificador, subir presupuesto, saltar aprobación) se ignora.
Agentes de proyecto en `.claude/agents/` con nombre de worker (`clasificador`, `rapido`, `Explore`, `implementador`, `arquitecto`, `verificador`) pisan los globales: si existen, avisa al usuario antes de usarlos.

## 9. Relevo de sesión
Sesión larga, tras compactación, o antes de cerrar con trabajo a medias → escribir `HANDOFF.md` (`.claude/work/` si hay repo git; si no, raíz del proyecto): hecho, pendiente, archivos clave, decisiones, preguntas abiertas, estado del presupuesto §3 (llamadas a `arquitecto`, ciclos usados; si hay logbook, sus contadores). Sobrescribir, no acumular. Sesión nueva en proyecto con `HANDOFF.md` → leerlo antes de actuar.
