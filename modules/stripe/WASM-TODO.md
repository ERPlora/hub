# stripe — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_stripe/{models.py,services.py}`. El CRUD plano (alta/baja
de conexión, listados, mark_processed simple) ya está en SQL declarativo Tier 0
(`commands/*.sql`, `queries/*.sql`). Lo que sigue es lógica que **no** cabe en una sola
sentencia SQL (upsert idempotente, ramas condicionales, hashing, agregación) y debe
convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (lookups de idempotencia, fila existente), calcula y devuelve *intenciones*
> (filas a insertar/actualizar) que el runtime valida y persiste en una transacción.
> Importes con `quantize(0.01)`. `is_deleted=0` filtra siempre los lookups.

## 1. `record_charge`  (command `stripe.charges.record`)
Origen: `StripeService.record_charge`.
- Validar: `charge_id` no vacío (`missing_charge_id`); `currency` no vacío (`missing_currency`);
  `status ∈ {pending, succeeded, failed, canceled}` (`invalid_status`).
- Validar `connection_id` pertenece al hub y existe (`Stripe connection not found`).
- Parsear `amount` a Decimal (`invalid_amount`) y `created_at_stripe` ISO→datetime (`invalid_datetime`).
- **Upsert idempotente por `charge_id`** (único por hub):
  - Si existe → UPDATE: `amount`, `currency`, `status` siempre; `customer_email`,
    `payment_intent_id`, `payment_method`, `description`, `raw_event`, `created_at_stripe`
    **solo si el payload trae valor no vacío** (no pisar con vacío). `created=false`.
  - Si no existe → INSERT con todos los campos. `created=true`.
- Devolver `{id, charge_id, amount, currency, status, created}`.
- Requiere lookup previo SELECT-por-charge_id + rama INSERT/UPDATE condicional por campo
  → no es una sola sentencia.

## 2. `record_refund`  (command `stripe.refunds.record`)
Origen: `StripeService.record_refund`.
- Validar: `refund_id` no vacío (`missing_refund_id`); `status ∈ {pending, succeeded, failed}`
  (`invalid_status`).
- Validar `charge_id_internal` (FK interna) existe en el hub (`Stripe charge not found`).
- Parsear `amount` (`invalid_amount`) y `created_at_stripe` (`invalid_datetime`).
- **Idempotencia**: si ya existe un refund con ese `refund_id` (único por hub) → error
  `duplicate_refund` (NO upsert; el legacy rechaza el duplicado). Si no, INSERT.
- Devolver `{id, refund_id, charge_id, amount, status}`.
- Requiere lookup de duplicado previo al INSERT → no es una sola sentencia.

## 3. `record_webhook_event`  (command `stripe.webhooks.record`)
Origen: `StripeService.record_webhook_event`.
- Validar: `event_id` (`missing_event_id`), `event_type` (`missing_event_type`),
  `payload` no nulo (`missing_payload`).
- Validar `connection_id` pertenece al hub (`Stripe connection not found`).
- Parsear `occurred_at` ISO→datetime (`invalid_datetime`).
- **Idempotencia (clave del módulo)**: Stripe reintenta entregas. Si ya existe un evento
  con ese `event_id` (único por hub) → **no-op** y devolver el existente con `duplicate=true`.
  Si no → INSERT con `status='received'` y devolver `duplicate=false`.
- Requiere lookup de idempotencia previo + rama no-op → no es una sola sentencia.

## 4. `mark_webhook_processed` — rama de fallo (command `stripe.webhooks.mark_processed`)
Origen: `StripeService.mark_webhook_processed`.
- El caso feliz (sin `error_message`) ya está en `commands/webhook_mark_processed.sql`
  (UPDATE → `status='processed'`, `processed_at=:now`).
- **Rama de fallo** (cuando el payload trae `error_message` no vacío): UPDATE a
  `status='failed'` + persistir `error_message`. Es condicional sobre el payload, por lo
  que la rama de fallo se mueve al handler (o a un segundo command si se prefiere Tier 0).
- Guard adicional del legacy: si el evento no existe → error `not_found` (en SQL el UPDATE
  simplemente afecta 0 filas; el runtime debe traducir rowcount=0 a `not_found`).

## 5. `get_charges_summary`  (query/command `stripe.charges.summary`)
Origen: `StripeService.get_charges_summary`.
- Validar `period_days > 0` (`invalid_period`).
- `since = now - period_days días`.
- Agregar **todos** los cargos del hub con `created_at >= since`:
  - `total_charges` = nº de cargos.
  - `by_status` = conteo por `status`.
  - `by_currency_amount` = Σ `amount` por `currency` (quantize 0.01).
  - `by_currency_succeeded` = Σ `amount` por `currency` solo `status='succeeded'` (quantize 0.01).
- Agregar refunds en la misma ventana (`status='succeeded'`): `refund_count`, `refund_amount`
  (quantize 0.01).
- Devolver `{period_days, since, total_charges, by_status, by_currency_amount,
  by_currency_succeeded, refund_count, refund_amount}`.
- Agregación multi-grupo (por status y por currency) + ventana temporal → en el legacy se
  hace en Python por portabilidad SQLite↔Postgres; va a WASM (lee filas vía runtime, agrega).

## 6. Hash del webhook secret (capacidad host, parte de `record_connection`)
Origen: `StripeConnection.webhook_secret_hash` (se guarda solo el **hash**, nunca el valor crudo).
- El alta de conexión (`commands/connection_create.sql`) inserta `webhook_secret_hash=''`.
- Si el alta debe aceptar y **hashear** un webhook signing secret entrante, el hashing es
  una capacidad del host/WASM (no SQL): recibir el secreto en claro, derivar el hash y
  devolver solo el hash al runtime para persistir. El secreto en claro nunca se almacena.
- Además, la comprobación previa de duplicado `(hub, account_id)` antes del INSERT
  (`duplicate_account`) es un lookup previo; en Tier 0 se delega al índice único
  `uq_stripe_conn_hub_acct` (el runtime traduce la violación de unicidad a `duplicate_account`).

## 7. Integración externa con la API de Stripe (fuera de alcance del CRUD)
- El módulo legacy **solo persiste** lo observado (cargos/refunds/eventos vía API o webhook);
  no inicia checkouts/charges contra Stripe en este código. Cualquier llamada saliente real
  a la API de Stripe (crear PaymentIntent, emitir refund, verificar firma de webhook con el
  signing secret) es Tier 1 (`http.fetch` mediado por el host) + verificación de firma en
  WASM, y queda documentada aquí como ampliación futura, no implementada en el legacy.
