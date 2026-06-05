# rules_triggers — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_rules_triggers/{models.py,services.py}`. El CRUD plano
(crear/activar/desactivar trigger, desactivar regla) ya está en SQL declarativo Tier 0
(`commands/*.sql`). Lo que sigue es validación compleja, evaluación condicional, dispatch
de acciones, batch atómico y agregación — lógica que **no** cabe en una sola sentencia SQL
y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. Las queries `rules.list`/`rules.get`/`rule_get`
> y los contadores de uso (counter UPSERT) son capacidades del runtime, no del WASM.

## Operadores de condición (núcleo compartido)
Origen: `services._CONDITION_OPS` + `_lookup` + `_evaluate_condition` + `_evaluate_all`.
Una condición tiene forma `{"field": "amount", "op": "gt", "value": 100}`. `field` es una
ruta con puntos dentro de `input_data` (resolución best-effort; ausente ⇒ `None`).
Operadores soportados:
- `eq` `ne` `gt` `gte` `lt` `lte` (comparación; `gte`→>=, `lte`→<=).
- `in` (a ∈ b) / `nin` (a ∉ b) — b es lista (None ⇒ []).
- `contains` (b ⊂ a, a es string; None ⇒ "").
- `exists` (a is not None) / `truthy` (bool(a)) / `falsy` (not bool(a)).
Semántica AND: **todas** las condiciones deben cumplir; lista vacía ⇒ `True`. Cualquier
`TypeError`/`ValueError` al comparar ⇒ la condición es `False` (no lanza). Operador
desconocido ⇒ `False`.

## Dispatch de acciones (placeholder en v1.0.0)
Origen: `services._execute_actions`. En v1.0.0 **no** llama a otros módulos: por cada
acción `{type, params}` produce `{index, type, params, ok:true, placeholder:true}`. Si la
acción no es dict ⇒ `{index, type:null, ok:false, reason:"not_a_dict"}`. Cuando se conecte
de verdad, el dispatch será cross-módulo vía **eventos/commands públicos** (nunca imports):
el WASM devuelve la intención y el runtime emite el evento o invoca el command destino.

## 1. `create_rule`  (command `rules_triggers.rules.create`)
Origen: `RulesService.create_rule`.
- Validar: `code`/`name` no vacíos (JSON Schema ya lo exige); `conditions` es lista;
  `actions` lista **no vacía** y cada acción con `type` no vacío (JSON Schema lo exige,
  pero el handler revalida — Rust es la autoridad).
- Unicidad de `code` por hub: leer `rules_triggers.rules` por code (query del runtime) →
  si existe ⇒ error `duplicate_code`. (El índice `ix_rt_rule_hub_code` es la última red.)
- Si viene `trigger_id`: validar UUID (`invalid_uuid`) y que el trigger exista
  (`trigger_not_found`) — lectura vía `rules_triggers.triggers` por id.
- Serializar `conditions`/`actions` a JSON y emitir intención INSERT (id/hub_id/created_by/
  updated_by/now por el runtime; `is_active=1`, `total_evaluations=0`, `total_matches=0`).
- Emite `rules_triggers.rule.created`.
- Devolver `{id, code, priority, actions_count, stop_on_match}`.

## 2. `update_rule`  (command `rules_triggers.rules.update`)
Origen: `RulesService.update_rule`. Update parcial de campos mutables.
- Campos permitidos: `name`, `description`, `priority`, `conditions`, `actions`,
  `stop_on_match`, `is_active`, `trigger_id`. Campos desconocidos se ignoran.
- Cargar la regla (scope hub_id) ⇒ si no existe `not_found`.
- Si viene `actions`: lista no vacía y cada una con `type` (`empty_actions`/`invalid_action`).
- Si viene `conditions`: debe ser lista (`invalid_conditions`).
- Si viene `trigger_id` no vacío: validar UUID + existencia (`invalid_uuid`/`trigger_not_found`).
- Emitir intención UPDATE solo de los campos presentes (+ `updated_by`/`updated_at` por runtime);
  `conditions`/`actions` se reserializan a JSON. Emite `rules_triggers.rule.updated`.
- Devolver `{id, updated:[campos cambiados]}`.

## 3. `evaluate_rules`  (command `rules_triggers.rules.evaluate`)  ← núcleo del módulo
Origen: `RulesService.evaluate_rules`. Evalúa las reglas activas contra `input_data`,
itera por `priority` asc (menor primero), persiste un `RuleEvaluation` por regla y actualiza
contadores. Es **batch atómico** sobre N reglas → todo en una transacción del runtime.
- Validar `input_data` es objeto (`invalid_input`); si viene `trigger_id` validar UUID.
- Cargar reglas activas (filtradas por `trigger_id` si se pasó), ordenadas por priority asc
  — lectura vía query del runtime (`rules_triggers.rules.list`).
- Si hay `trigger_id`: cargar el trigger y emitir intención UPDATE `last_fired_at = now`,
  `fire_count += 1` (contador → capacidad del runtime, sin ventana SELECT→UPDATE).
- Por cada regla, medir tiempo (capacidad "reloj" del host):
  - `matched = _evaluate_all(conditions, input_data)` (ver núcleo de operadores arriba).
  - Si matchea: `executed = _execute_actions(actions)`; `output = {actions_executed: executed}`.
    Si no: `output = {}`.
  - Emitir intención INSERT en `rules_triggers_evaluation` (rule_id, trigger_id, evaluated_at=now,
    matched, input_data JSON, output JSON, execution_time_ms, error_message="").
  - Emitir intención UPDATE de la regla: `total_evaluations += 1`, y si matchea `total_matches += 1`.
  - Si `matched && stop_on_match` ⇒ **cortar** la iteración (no evaluar reglas de menor prioridad).
- Emite `rules_triggers.rules.evaluated`.
- Devolver `{evaluated:N, matched:M, stopped:bool, results:[{rule_id,code,matched,actions_executed,execution_time_ms}]}`.

## 4. `test_rule`  (command `rules_triggers.rules.test`)  — sin persistir
Origen: `RulesService.test_rule`. Evalúa **una** regla contra `input_data` SIN escribir nada
(útil para previsualizar en el editor). La regla se carga aunque esté inactiva.
- Validar `input_data` es objeto (`invalid_input`); cargar regla por id (`not_found`).
- `matched = _evaluate_all(...)`; `executed = _execute_actions(...)` solo si matchea; medir ms.
- **No** emite eventos ni filas. Devolver `{rule_id, code, matched, actions_executed, execution_time_ms}`.
- Nota: es de solo-lectura/cálculo. Va a WASM por reusar el motor de condiciones, no por mutar.

## 5. `get_rule_stats`  (no expuesto como command público — derivable en runtime/UI)
Origen: `RulesService.get_rule_stats`. Cálculo trivial sobre la fila de la regla:
`match_rate = total_matches / total_evaluations` (0.0 si total=0), redondeado a 4 decimales.
- No requiere WASM dedicado: el dato está en `rules_triggers.rules.get`; el ratio lo calcula
  la UI o un helper del runtime. Documentado aquí para no perder la semántica del legacy.
  Si se prefiere centralizar, puede añadirse como función WASM `get_rule_stats` que recibe la
  fila y devuelve `{rule_id, code, total_evaluations, total_matches, match_rate, is_active, priority}`.
