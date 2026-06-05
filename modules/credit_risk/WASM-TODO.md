# credit_risk — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_credit_risk/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
`customer_register`, `customer_block`, `customer_unblock`, `alert_acknowledge`.

Lo que sigue es lógica de cálculo / recálculo de exposición / scoring / disparo de alertas
que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas leídas por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, eventos a emitir)
> que el runtime valida y persiste en una transacción. Todos los importes son decimales con
> `quantize(0.01)`; el score es entero en `[0, 1000]`.

Convención de exposición (legacy `record_event`):
- `invoice_issued`  → `current_exposure += amount`
- `payment_received`→ `current_exposure -= amount`, con suelo en 0 (`max(0, ...)`)
- `late_payment`, `limit_exceeded`, `manual_review`, `score_updated` → no cambian exposición
- `available_credit = max(0, credit_limit - current_exposure)`

---

## 1. `record_event`  (command `credit_risk.events.record`)
Origen: `CreditRiskService.record_event`.
- Validar `event_type` ∈ EVENT_TYPES (también lo cubre el JSON Schema).
- Leer el `credit_risk_customer` (binds: id, hub_id) → error `not_found` si no existe.
- Recalcular `current_exposure` según la convención de arriba.
- Emitir intención `_insert_event` (fila `credit_risk_event`: event_type, amount, description,
  occurred_at=now, reference).
- **Disparo de alertas** (sobre la exposición nueva, solo si `credit_limit > 0`):
  - `invoice_issued` / `manual_review`:
    - si `exposure > limit` → alerta `limit_exceeded` severidad `critical`
    - si no, si `exposure >= limit * 0.8` → alerta `limit_warning_80pct` severidad `warning`
  - `late_payment` → alerta `payment_overdue` severidad `warning` (siempre)
- Persistir cabecera (`current_exposure`) + evento + N alertas en una transacción.
- Devolver `{id, customer_credit_id, event_type, amount, current_exposure, available_credit,
  triggered_alert_ids:[...]}`.
- Emitir `credit_risk.event.recorded` y un `credit_risk.alert.triggered` por cada alerta creada.

## 2. `update_score`  (command `credit_risk.customers.update_score`)
Origen: `CreditRiskService.update_score`.
- Leer el customer → `not_found` si no existe.
- Validar `new_score` ∈ `[0, 1000]` (también JSON Schema).
- Setear `credit_score = new_score`, `score_calculated_at = now`.
- Emitir intención `_insert_event` (`score_updated`, amount=0, description=`"Score {old} -> {new}"`).
- **Alerta por caída**: si `old_score > 0` y `(old_score - new_score) >= 100` → alerta
  `score_dropped` severidad `warning`.
- Persistir cabecera + evento + alerta opcional en una transacción.
- Devolver `{id, credit_score, score_calculated_at, triggered_alert_id|null}`.
- Emitir `credit_risk.score.updated` y, si hubo alerta, `credit_risk.alert.triggered`.

## 3. `update_limit`  (command `credit_risk.customers.update_limit`)
Origen: `CreditRiskService.update_limit`.
- Leer el customer → `not_found` si no existe.
- Validar `new_limit >= 0` y `reason` no vacío (JSON Schema cubre ambos).
- Setear `credit_limit = new_limit`.
- Emitir intención `_insert_event` (`manual_review`, amount=0,
  description=`"Limit changed {old_limit} -> {new_limit}: {reason}"`).
- Persistir cabecera + evento en una transacción.
- Devolver `{id, credit_limit, available_credit}`.
- Emitir `credit_risk.limit.updated`.
- Nota: es WASM (no Tier 0) porque escribe atómicamente cabecera + un `credit_risk_event`
  de auditoría que el SQL declarativo de una sola sentencia no puede generar.

## 4. `check_limit`  (command `credit_risk.customers.check_limit`, solo lectura)
Origen: `CreditRiskService.check_limit`. Permiso `view_risk`. No muta nada (sin transacción);
es un cálculo puro sobre la fila leída por el runtime.
- Leer el customer → `not_found` si no existe.
- Parsear `amount` (≥ 0; JSON Schema cubre el tipo).
- `new_exposure = current_exposure + amount`; `limit = credit_limit`.
- Reglas (orden exacto del legacy):
  1. `status == 'blocked'` → `{ok:false, would_exceed:true, suggested_action:'unblock_customer'}`
  2. `new_exposure > limit` → `{ok:false, would_exceed:true, suggested_action:'request_override'}`
  3. `status == 'on_hold'` → `{ok:false, would_exceed:false, suggested_action:'request_override'}`
  4. `limit > 0` y `new_exposure >= limit * 0.8` → `{ok:true, would_exceed:false, suggested_action:'warn'}`
  5. resto → `{ok:true, would_exceed:false, suggested_action:'proceed'}`
- Devolver `{ok, available: max(0, limit - current_exposure), would_exceed, suggested_action}`.
- `suggested_action` ∈ `proceed | warn | request_override | unblock_customer`.
- Se modela como command-con-handler (no query) porque la respuesta es un veredicto calculado,
  no filas de tabla. No emite eventos.

---

## Notas sobre los commands Tier 0 que conservan un matiz legacy
Estos ya están en SQL declarativo, pero el legacy además escribía un `credit_risk_event`
`manual_review` de auditoría que la sentencia única no genera. Si se quiere conservar ese
rastro, promover a un handler WASM que añada la intención `_insert_event`:

- `customer_block`  → evento `manual_review` description=`"Customer blocked: {reason}"`.
- `customer_unblock`→ evento `manual_review` description=`"Customer unblocked"`.

Las guardas de estado (`already_blocked` / `not_blocked`) hoy se expresan como predicado en el
`WHERE` del UPDATE (filas afectadas = 0 ⇒ no-op). Si se requiere un error explícito en vez de
no-op, también van al handler. No bloqueante para el CRUD básico.
