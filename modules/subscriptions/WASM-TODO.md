# subscriptions — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_subscriptions/{models.py,services.py}`. El CRUD plano y las
transiciones simples ya están en SQL declarativo Tier 0 (`commands/plan_create.sql`,
`commands/cycle_mark_paid.sql`). Lo que sigue es **aritmética de fechas/periodos**,
guardas de estado dependientes de datos leídos y **batch sobre N filas** que no cabe en
una sola sentencia SQL → handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas que el runtime le
> lee (plan, suscripción, ciclos) y devuelve *intenciones* (filas a insertar/actualizar,
> sub-comandos a ejecutar) que el runtime valida, inyecta `hub_id`/auditoría y persiste en
> una transacción. "hoy" se obtiene de la capacidad reloj del host (no del WASM).

## Constantes compartidas (de `models.py`)
- `BILLING_PERIOD_DAYS = { monthly: 30, quarterly: 90, yearly: 365 }`. El periodo se calcula
  como ventana de días fija (no aritmética de calendario): `period_delta(billing_period)`.
- `SUBSCRIPTION_STATUSES = (trialing, active, past_due, cancelled, expired)`.
- `CYCLE_STATUSES = (pending, invoiced, paid, failed)`.
- Helper `parse_iso_date`: acepta `null`/`""` → `None`, o `YYYY-MM-DD`.

## 1. `create_subscription`  (command `subscriptions.subscriptions.create`)
Origen: `SubscriptionService.create_subscription`.
- Runtime lee el `Plan` por `plan_id` (scope hub). Si no existe → error `plan_not_found`.
  Si `plan.is_active == 0` → error `inactive_plan`.
- Parsear `start_date` (payload) → `sd`; si vacío/null → `hoy`. Error `invalid_date` si no parsea.
- `period_len = period_delta(plan.billing_period)`.
- **Bifurcación trial**:
  - Si `plan.trial_days > 0`: `status='trialing'`, `trial_end = sd + trial_days días`,
    `current_period_start = NULL`, `current_period_end = NULL`.
  - Si no: `status='active'`, `trial_end = NULL`, `current_period_start = sd`,
    `current_period_end = sd + period_len`.
- Emitir intención INSERT en `subscriptions_subscription` con todos los campos del cliente
  (`customer_name/email/tax_id`), `plan_id`, `status`, `start_date=sd` y las fechas calculadas.
- Devolver `{id, plan_id, customer_name, status, start_date, trial_end,
  current_period_start, current_period_end}`. Emite `subscriptions.subscription.created`.

## 2. `activate_subscription`  (command `subscriptions.subscriptions.activate`)
Origen: `SubscriptionService.activate_subscription`.
- Runtime lee la suscripción + su plan. Si no existe sub → error `not_found`; plan ausente
  → error `plan_not_found`.
- **Guarda de estado**: solo `status=='trialing'` puede activarse; si no → error `invalid_state`.
- `period_len = period_delta(plan.billing_period)`; `today = hoy`.
- `start = trial_end` si `trial_end` existe y `trial_end > today`, si no `today`.
- `end = start + period_len`.
- Emitir UPDATE: `status='active'`, `current_period_start=start`, `current_period_end=end`
  (+ auditoría `updated_by/updated_at`).
- Devolver `{id, status, current_period_start, current_period_end}`.
  Emite `subscriptions.subscription.activated`.

## 3. `cancel_subscription`  (command `subscriptions.subscriptions.cancel`)
Origen: `SubscriptionService.cancel_subscription`.
- Runtime lee la suscripción. Si no existe → error `not_found`.
- **Guarda**: si `status ∈ (cancelled, expired)` → error `already_cancelled`.
- `today = hoy`. Siempre: `status='cancelled'`, `cancelled_at=today`,
  `cancellation_reason=reason` (payload).
- Si `immediate == true`: además `current_period_end = today`, y si
  `trial_end` existe y `trial_end > today` → `trial_end = today` (trunca el periodo para que
  la lógica de renovación no genere más ciclos y permita prorrateo de devolución aguas abajo).
- Si `immediate == false`: se preservan las fechas de periodo (la sub sigue "vigente" hasta
  `current_period_end`/`trial_end` pero ya no renueva).
- Emitir UPDATE con los campos anteriores. Devolver `{id, status, cancelled_at,
  current_period_end, immediate}`. Emite `subscriptions.subscription.cancelled`.

## 4. `generate_billing_cycle`  (command `subscriptions.cycles.generate`)
Origen: `SubscriptionService.generate_billing_cycle`. **Multi-fila atómico** (inserta ciclo
+ actualiza cabecera) → WASM.
- Runtime lee la suscripción + su plan. sub ausente → `not_found`; plan ausente → `plan_not_found`.
- **Guarda**: si `status ∈ (cancelled, expired)` → error `invalid_state`.
- `period_len = period_delta(plan.billing_period)`.
- **Anchor**: `current_period_end` si está, si no `trial_end`, si no `start_date`.
- `period_start = anchor`; `period_end = period_start + period_len`.
- Emitir 2 intenciones en la **misma transacción**:
  1. INSERT en `subscriptions_billing_cycle`: `subscription_id`, `period_start`, `period_end`,
     `amount = plan.price` (precio congelado en la generación), `status='pending'`.
  2. UPDATE en la suscripción: `current_period_start=period_start`,
     `current_period_end=period_end`; y si `status=='trialing'` → `status='active'`
     (facturar auto-activa una trial).
- Devolver `{id (cycle), subscription_id, period_start, period_end, amount, status}`.
  Emite `subscriptions.cycle.generated`.

## 5. `process_renewals`  (command `subscriptions.subscriptions.process_renewals`, tarea programada)
Origen: `SubscriptionService.process_renewals`. **Batch sobre N suscripciones** → WASM.
- `today = hoy`. Runtime lee todas las suscripciones del hub con `status=='active'`.
- Por cada una: si `current_period_end` es NULL o `> today` → saltar.
- Para las que vencen (`current_period_end <= today`): invocar la lógica de la pieza 4
  (`generate_billing_cycle`) para esa suscripción (genera ciclo + avanza periodo).
- Acumular los `subscription_id` de los que generaron ciclo correctamente.
- Devolver `{ok:true, generated:N, subscription_ids:[...]}`.
  Emite `subscriptions.renewals.processed`.
- En legacy NO era un `@action` (lo lanzaba el scheduler). Aquí se expone como command bajo
  `manage_sub`; el scheduler/cron del runtime puede invocarlo. No requiere payload.

## Notas de portado
- `features` del plan: en legacy es JSON (dict) en columna `JSON`. En SQLite se almacena como
  TEXT (JSON string). El alta Tier 0 (`plan_create.sql`) recibe `features` ya serializado como
  string ('{}' por defecto vía schema). Si la UI envía un objeto, el SDK/runtime debe serializarlo
  antes del bind.
- Todas las fechas viajan como ISO `YYYY-MM-DD` (TEXT). El reloj ("hoy") es capacidad del host;
  el WASM no lo inventa.
- `amount`/`price` son decimales con 2 posiciones (NUMERIC); congelar el precio del plan al generar
  el ciclo (no recalcular contra el plan actual si este cambia de precio después).
