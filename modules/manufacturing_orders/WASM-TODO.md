# manufacturing_orders — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_manufacturing_orders/{models.py,services.py}`. El CRUD plano y
las transiciones de estado simples (release/start/complete/cancel) ya están en SQL declarativo
Tier 0 (`commands/order_*.sql`, con guard de estado en el `WHERE status='...'`). Lo que sigue es
lógica de contador atómico / alta batch / derivación de estado / agregación que **no** cabe en una
sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime,
> calcula y devuelve *intenciones* (comandos internos `_insert_order` / `_insert_material` /
> `_set_material_consumption` a ejecutar) que el runtime valida y persiste en una transacción.
> Las cantidades son decimales con `quantize(0.001)` (la legacy usa `Numeric(15,3)`).

## 1. `create_mo`  (command `manufacturing_orders.orders.create`)
Origen: `ManufacturingOrderService.create_mo` + `generate_mo_number`.
- Validar (el JSON Schema `schemas/create_mo.json` ya cubre tipos/required, pero el handler
  revalida la lógica de negocio):
  - `product_ref` no vacío (tras strip).
  - `quantity_planned` parseable y `> 0`.
  - `materials` lista **no vacía**; por cada material: `material_ref` no vacío (strip),
    `quantity_planned` parseable y `> 0`, `unit` (default `"unit"`).
  - `scheduled_date` / `due_date`: ISO `YYYY-MM-DD` o vacío → NULL.
- Generar `mo_number` atómico → ver pieza 5 (counter). Formato `MO-YYYYMMDD-NNNN`.
- Emitir `_insert_order` con la cabecera (status='draft', quantity_produced=0, started_at/
  completed_at = NULL) usando el `mo_number` y un `new_id` generado por el handler.
- Por cada material emitir `_insert_material` (status='pending', quantity_consumed=0) con su
  propio `new_id` y el `mo_id` de la cabecera recién creada.
- Todo dentro de una sola transacción (cabecera + N líneas). Si una línea es inválida → abortar
  todo (la legacy hace `return self.error(...)` dentro del `atomic()`).
- Devolver `{id, mo_number, product_ref, quantity_planned, status:'draft', materials_count}`
  y emitir `manufacturing_orders.mo.created`.

## 2. `record_consumption`  (command `manufacturing_orders.materials.record_consumption`)
Origen: `ManufacturingOrderService.record_consumption`.
- Cargar la línea `MaterialConsumption` por `material_consumption_id` (scope hub). Si no existe → error `not_found`.
- Validar `quantity_consumed` parseable y `>= 0` (el schema ya fuerza `minimum:0`).
- **Guard cross-fila**: cargar la orden padre (`mo_id`); si no existe → error `mo_not_found`;
  su `status` debe ser `released` o `in_progress`, si no → error `invalid_state`
  ("Cannot record consumption on a {status} order").
- **Derivar el estado de la línea** (lógica de negocio, no cabe en el UPDATE solo):
  `status = 'consumed'` si `quantity_consumed >= quantity_planned`, si no `status = 'short'`.
- Emitir `_set_material_consumption` con `quantity_consumed` y el `status` derivado.
- Devolver `{id, material_ref, quantity_consumed, status}` y emitir
  `manufacturing_orders.material.consumed`.

## 3. `get_mo_summary`  (command `manufacturing_orders.orders.summary`, solo lectura)
Origen: `ManufacturingOrderService.get_mo_summary`.
- Validar `period_days > 0` (schema: `minimum:1`).
- Ventana: `created_at >= now - period_days`.
- Agregados sobre `manufacturing_orders_order` del hub dentro de la ventana:
  - `by_status`: conteo agrupado por `status` → `{status: n}`.
  - `total`: suma de los conteos.
  - `total_planned`: `Σ quantity_planned` (coalesce 0).
  - `total_produced`: `Σ quantity_produced` (coalesce 0).
- Es agregación multi-fila con group-by + sumatorios y formateo decimal; va a WASM (el runtime
  le pasa las filas leídas o expone una capacidad de agregación). NO muta nada.
- Devolver `{period_days, total, by_status, total_planned, total_produced}` (decimales como string).

## 4. Transiciones de ciclo de vida (Tier 0 — ya en SQL, sin WASM)
Para referencia: `release_mo` (draft→released), `start_mo` (released→in_progress + started_at),
`complete_mo` (in_progress→completed + quantity_produced + completed_at) y `cancel_mo`
(cualquier estado salvo completed/cancelled) están resueltas como UPDATE con guard de estado en el
`WHERE`. El runtime interpreta "0 filas afectadas" como conflicto de estado (`invalid_state`),
equivalente a los `self.error(... invalid_state)` de la legacy.

### 4.1 Rastro textual del motivo de cancelación (Tier 1, no crítico)
Origen: `cancel_mo(reason=...)` que hacía `notes = f"{notes}\n[CANCELLED] {reason}"`.
- `commands/order_cancel.sql` (Tier 0) **no** conserva ese append textual; solo marca el estado.
- Si se quiere conservar el audit-trail (`[CANCELLED] {reason}` en `notes`), moverlo a un handler
  WASM que componga el nuevo `notes` (lectura del valor actual + append) y emita un `_set_*`
  dedicado. No bloqueante.

## 5. Contador atómico de nº de orden (`generate_mo_number`)
Origen: `ManufacturingOrderCounter` + `generate_mo_number` (UPSERT `INSERT ... ON CONFLICT
DO UPDATE SET last_number = last_number + 1 RETURNING last_number`). Formato `MO-YYYYMMDD-NNNN`
(NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres — un único round-trip.
- En hub-next se resuelve como capacidad del runtime (counter UPSERT sobre
  `manufacturing_orders_counter` por `(hub_id, day)`) invocada por el handler `create_mo`; el WASM
  solo formatea `MO-{day}-{n:04d}` con el número devuelto.
- La `UniqueConstraint(hub_id, mo_number)` (índice `uq_mo_hub_number`) es el guard adicional.
