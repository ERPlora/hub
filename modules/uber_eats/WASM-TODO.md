# uber_eats — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_uber_eats/{models.py,services.py}`. El CRUD plano (alta de
tienda, cambio de estado de tienda, marcar evento procesado) ya está en SQL declarativo
Tier 0 (`commands/store_create.sql`, `store_update_status.sql`, `event_mark_processed.sql`).
Lo que sigue es lógica de **idempotencia**, **numeración atómica**, **upsert**, **guardas
de ciclo de vida** y **agregación** que no cabe en una sola sentencia SQL y debe convertirse
en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos que el runtime le
> pasa (filas leídas por queries existentes), calcula y devuelve *intenciones* (qué comando
> interno `_insert_*` / `_set_*` / `_update_*` ejecutar y con qué binds) que el runtime valida
> y persiste en una transacción. La numeración atómica se resuelve como capacidad del runtime
> (counter UPSERT), no leyendo/contando filas dentro del WASM.

Comandos internos disponibles para que los handlers compongan intenciones:
`uber_eats._insert_order`, `uber_eats._set_order_status`, `uber_eats._insert_menu`,
`uber_eats._update_menu`, `uber_eats._insert_event`.
Queries disponibles para la lectura previa: `uber_eats.stores.list`, `uber_eats.orders.list`,
`uber_eats.orders.get`, `uber_eats.menus.list`, `uber_eats.events.list`.

---

## 1. `import_order`  (command `uber_eats.orders.import`)
Origen: `UberEatsService.import_order` + `models.generate_order_number`.
- Validar tienda: el `store_id` (PK interno) debe existir para el hub (si no → error `store_not_found`).
  El runtime resuelve la existencia leyendo `uber_eats.stores.list`/`orders.get`-equivalente;
  el handler recibe la fila de la tienda (incluida su `currency`).
- **Idempotencia por `uber_order_id`**: si ya existe un pedido con ese `uber_order_id` para el
  hub, NO insertar; devolver `{id, uber_order_id, order_number, status, created:false}` del
  existente. (La unicidad la respalda el índice `ix_ue_order_hub_uid`; el handler debe consultar
  primero para devolver `created:false` en vez de provocar un error de índice.)
- Parsear `total_amount` (string → Decimal) y aplicar `quantize(0.01)`. Entrada inválida →
  error `invalid_amount`.
- Parsear `created_at_uber` (ISO-8601, acepta sufijo `Z`; vacío/None → NULL). Inválido → `invalid_date`.
- `currency`: si viene vacío en el payload, heredar `store.currency`.
- **Generar `order_number` atómico** = `UE-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4
  dígitos). En el legacy se hacía contando filas con `LIKE 'UE-<día>-%'` + `UniqueConstraint`
  como guarda de carrera. En hub-next debe resolverse como **counter UPSERT del runtime** (sin
  ventana SELECT→INSERT); el WASM solo formatea `UE-{día}-{n:04d}` con el número devuelto.
- Emitir intención `_insert_order` con todos los binds (`status='created'`).
- Devolver `{id, uber_order_id, order_number, status, total_amount, created:true}`.
- Evento de salida: `uber_eats.order.imported`.

## 2. `update_order_status`  (command `uber_eats.orders.update_status`)
Origen: `UberEatsService.update_order_status`.
- El JSON Schema ya restringe `new_status` al enum de estados; las **guardas de ciclo de vida**
  van aquí (devuelven códigos de error específicos, no caben en SQL):
  - `order.status == 'cancelled'` → error `cancelled_locked` ("Cannot transition a cancelled order").
  - `order.status == 'delivered'` y `new_status != 'delivered'` → error `delivered_locked`.
- Si pasa las guardas: emitir `_set_order_status` con `{id, status:new_status, customer_notes}`
  (customer_notes sin cambios — se reenvía el actual leído del pedido).
- Devolver `{id, uber_order_id, status}`.
- Evento de salida: `uber_eats.order.status_changed`.

## 3. `cancel_order`  (command `uber_eats.orders.cancel`)
Origen: `UberEatsService.cancel_order`.
- Guardas:
  - `order.status == 'delivered'` → error `delivered_locked` ("Cannot cancel a delivered order").
  - `order.status == 'cancelled'` → error `already_cancelled`.
- Recomponer `customer_notes`: si `reason` no vacío, anexar `"[CANCELLED] {reason}"`
  (`f"{notes}\n[CANCELLED] {reason}".strip()` si ya había notas; si no, solo la nota).
- Emitir `_set_order_status` con `{id, status:'cancelled', customer_notes: <recompuesto>}`.
- Devolver `{id, uber_order_id, status:'cancelled'}`.
- Evento de salida: `uber_eats.order.cancelled`.

## 4. `sync_menu`  (command `uber_eats.menus.sync`)
Origen: `UberEatsService.sync_menu`. **Upsert** por `uber_menu_id`.
- Validar tienda (igual que en import_order → `store_not_found`).
- Leer si existe un menú con ese `uber_menu_id` para el hub (vía `uber_eats.menus.list` o lookup
  equivalente que el runtime pase al handler).
  - No existe → emitir `_insert_menu` (`sync_status='synced'`, `last_synced_at=now`), `created:true`.
  - Existe → emitir `_update_menu` con `{id, name, items_count}` (refresca name/items_count/
    last_synced_at/sync_status='synced'), `created:false`.
- `items_count` → entero (default 0).
- Devolver `{id, uber_menu_id, name, items_count, sync_status:'synced', created}`.
- Evento de salida: `uber_eats.menu.synced`.

## 5. `record_event`  (command `uber_eats.events.record`)
Origen: `UberEatsService.record_event`. **Ingesta idempotente** de webhooks.
- Validar tienda (→ `store_not_found`). El enum de `event_type` ya lo valida el JSON Schema.
- **Idempotencia por `event_id`**: si ya existe un evento con ese `event_id` para el hub, NO
  insertar; devolver `{id, event_id, event_type, status, created:false}` del existente.
- Parsear `occurred_at` (ISO-8601; vacío/None → `now`). Inválido → error `invalid_date`.
- Serializar `payload` (objeto JSON) a texto para la columna `payload`.
- Emitir `_insert_event` (`status='received'`).
- Devolver `{id, event_id, event_type, status:'received', created:true}`.
- Evento de salida: `uber_eats.event.recorded`.
- Nota: `mark_event_processed` (transición simple `received→processed` + `processed_at=now`) SÍ
  está en Tier 0 (`event_mark_processed.sql`); no necesita WASM.

## 6. `store_summary`  (command `uber_eats.stores.summary`, solo lectura/agregación)
Origen: `UberEatsService.get_store_summary`. Agregación sobre N pedidos → no es una sola query.
- Validar tienda (→ `store_not_found`).
- Ventana: `cutoff = now - period_days días` (period_days ≥ 0; default 30).
- Leer los pedidos de la tienda con `created_at >= cutoff` (vía `uber_eats.orders.list` filtrada
  por `store_id`; el filtro por fecha lo aplica el handler sobre la lista, o el runtime al pasar
  los datos).
- Calcular:
  - `orders_by_status`: dict con conteo por cada estado de `ORDER_STATUSES`
    (`created/accepted/preparing/ready/delivered/cancelled`), inicializado a 0.
  - `revenue`: Σ `total_amount` de los pedidos **no cancelados**, con `quantize(0.01)`.
- Devolver `{store_id, uber_store_id, name, period_days, orders_total, orders_by_status,
  revenue (string), currency}`.
- Es solo lectura: no emite intenciones de escritura ni eventos.

---

## Notas de portabilidad / decisiones
- **Numeración atómica** (pieza 1): es el único punto que exige una capacidad del runtime
  (counter UPSERT) en vez de cálculo puro; documentado como decisión pendiente igual que en
  `quotes`/`m_quotes`. Formato `UE-{YYYYMMDD}-{n:04d}`.
- **Decimales**: `total_amount` y `revenue` se manejan como decimales con `quantize(0.01)`
  (no enteros de céntimos en el legacy de uber_eats; mantener Decimal/string para no perder
  el contrato de los modelos).
- **JSON**: `items` (pedido), `payload` (evento) y `settings` (tienda) se almacenan como texto
  JSON en columnas TEXT; el handler serializa/deserializa, la BD no los interpreta.
- **Sin cross-módulo**: este módulo NO importa ni lee tablas de `sales`/`inventory`. Si en el
  futuro se quiere reflejar un pedido Uber como venta interna, se hará vía evento
  (`uber_eats.order.imported`) que un listener de `sales` consuma — nunca por import directo.
