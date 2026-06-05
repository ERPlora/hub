# workflows — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_workflows/{models.py,services.py}`. El CRUD plano de
workflows y las transiciones simples (activar/desactivar/borrar) ya están en SQL
declarativo Tier 0 (`commands/*.sql`). Lo que sigue es lógica de evaluación,
generación batch de filas y orquestación de ciclo de vida que **no** cabe en una
sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (el workflow y sus campos JSON), evalúa/calcula y devuelve *intenciones*
> (filas a insertar/actualizar) que el runtime valida y persiste en una transacción.
> Los campos JSON (`conditions`, `actions`, `trigger_config`, `input_data`, etc.) viajan
> como objetos/listas ya deserializados.

## 1. `execute_workflow`  (command `workflows.workflows.execute`)
Origen: `WorkflowService.execute_workflow`. **Toda** la lógica de ejecución vive aquí
porque toca varias tablas, evalúa condiciones, genera N pasos en batch y actualiza
contadores de la cabecera de forma atómica.

Entrada (binds que el runtime debe proveer al handler):
- `payload`: `{ workflow_id, input_data }` (validado contra `schemas/workflow_execute.json`).
- Lectura previa (el runtime ejecuta y pasa al WASM): la fila del workflow
  (`workflows.workflows.get`) — necesita `conditions`, `actions`, `total_runs`, `is_active`.
- Capacidades de host: reloj (`now` ISO datetime), generador de UUID (`new_id`) por cada
  fila a crear (1 run + N steps), `current_user_id`, `hub_id`.

Lógica (portada de `execute_workflow`):
1. Si el workflow no existe / `is_deleted` → error `not_found` (el runtime ya lo resuelve
   con la lectura previa; el WASM asume que recibe una fila válida).
2. `ctx = input_data or {}`. `now = host_now()`.
3. **Evaluar condiciones** (pieza 3) sobre `ctx`. `conditions_ok = all(eval(c, ctx))`;
   lista vacía ⇒ `True`.
4. Crear intención de `WorkflowRun` con `status='running'`, `started_at=now`,
   `input_data=ctx`, `output_data={}`, `error_message=''`.
5. Si `conditions_ok == False`:
   - run pasa a `status='cancelled'`, `completed_at=now`,
     `output_data={"reason":"conditions_not_met"}`.
   - **No** se generan pasos.
   - Aun así se actualiza la cabecera: `last_run_at=started_at`, `total_runs += 1`.
   - Devolver `{run_id, workflow_id, status:'cancelled', steps_count:0, reason:'conditions_not_met'}`.
6. Si `conditions_ok == True`:
   - Por cada acción `act` (índice `idx`) en `actions`, generar intención de `WorkflowStep`:
     `step_order=idx`, `step_type=act.type or 'unknown'`, `params=act.params or {}`,
     `started_at=now`, `status='done'`,
     `result={"placeholder":true,"action_index":idx,"type":act.type}`, `completed_at=now`.
     > NOTA v1.0.0: la ejecución real es un **placeholder** — los pasos se registran como
     > `done` pero NO se despacha la acción contra otros módulos. Cuando se implemente el
     > despacho real (vía contrato de eventos / commands públicos de otros módulos, NUNCA
     > imports), cada paso emitirá su propio command/event y `status` reflejará el resultado.
   - run pasa a `status='completed'`, `completed_at=now`,
     `output_data={"steps_executed": N}`.
   - Cabecera: `last_run_at=started_at`, `total_runs += 1`.
   - Devolver `{run_id, workflow_id, status:'completed', steps_count:N}`.
7. Todo lo anterior (insert run + N inserts step + update cabecera) lo persiste el runtime
   en **una transacción**; el WASM solo devuelve la lista de intenciones.
8. Emitir `workflows.run.completed` (declarado en `module.json`) con
   `{run_id, workflow_id, status, steps_count}`.

## 2. `evaluate_conditions`  (command `workflows.conditions.evaluate`, utilidad de lectura)
Origen: `WorkflowService.evaluate_conditions`. Pura: no escribe en BD, solo evalúa.
- Entrada: `{conditions: [...], context: {...}}` (validado por `schemas/conditions_evaluate.json`).
- Para cada `cond`: si no es objeto → `{ok:false, reason:'not_a_dict', cond}` y `result=false`.
  En otro caso evaluar (pieza 3) → `{ok, cond}`.
- `result = all(ok)`; lista vacía ⇒ `result=true`.
- Devolver `{result: <bool>, details: [...]}`.
- Es Tier 2 (no Tier 0) porque la evaluación con operadores y resolución de paths punteados
  no se expresa en una sentencia SQL.

## 3. Motor de evaluación de condiciones (compartido por 1 y 2)
Origen: `_CONDITION_OPS`, `_lookup`, `_evaluate_condition` en `services.py`.

Forma de una condición: `{"field": "amount", "op": "gt", "value": 100}`.

- **`_lookup(context, field)`**: resuelve un path punteado (`a.b.c`) sobre `context`
  (dict anidado). Si algún tramo falta o no es dict navegable → `None`. `field` vacío → `None`.
- **Operadores** (`op`, en minúsculas; desconocido ⇒ la condición evalúa `false`):
  | op       | semántica                                  |
  |----------|--------------------------------------------|
  | `eq`     | actual == value                            |
  | `ne`     | actual != value                            |
  | `gt`     | actual > value                             |
  | `gte`    | actual >= value                            |
  | `lt`     | actual < value                             |
  | `lte`    | actual <= value                            |
  | `in`     | actual in (value or [])                    |
  | `nin`    | actual not in (value or [])                |
  | `contains` | (value) in (actual or "")                |
  | `exists` | actual is not None                         |
  | `truthy` | bool(actual)                               |
  | `falsy`  | not bool(actual)                           |
- Cualquier `TypeError`/`ValueError` al aplicar el operador (p.ej. comparar tipos
  incompatibles) ⇒ la condición evalúa `false` (no propaga excepción).

## 4. Notas de portabilidad
- Los `enum` de `trigger_type` (manual/scheduled/event/webhook) y `status`
  (running/completed/failed/cancelled · step: pending/running/done/failed/skipped) ya se
  validan en los JSON Schemas / contrato; el WASM puede asumirlos válidos.
- El disparo automático por `scheduled`/`event`/`webhook` (programador, listeners) NO está
  en el legacy v1.0.0 (los workflows solo se ejecutan vía `execute_workflow` manual). Cuando
  se implemente, los triggers `event` se conectarán como `events.listen` en `module.json`
  y los `scheduled` como tarea programada del runtime; el cálculo del `next_run` y el matching
  trigger→workflow iría también a este handler.
