# multi_warehouse — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_multi_warehouse/{models.py,services.py}`. El CRUD plano y
la cancelación (guarda de estado expresable en `WHERE`) ya están en SQL declarativo
Tier 0 (`commands/transfer_cancel.sql` + queries). Lo que sigue es lógica condicional
multi-sentencia / batch / numeración atómica que **no** cabe en una sola sentencia SQL
y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, valida/calcula y devuelve *intenciones* (filas a insertar/actualizar, transiciones
> de estado) que el runtime valida y persiste en una transacción. Las cantidades usan
> decimales con 3 dígitos (`quantize(0.001)`); las comparaciones de cantidad son `>= 0`.

Choices (constantes):
- `WAREHOUSE_TYPES = ("main", "secondary", "store", "dropship")`
- `TRANSFER_STATUSES = ("draft", "in_transit", "received", "cancelled")`

---

## 1. `create_warehouse`  (command `multi_warehouse.warehouses.create`)
Origen: `MultiWarehouseService.create_warehouse`.
- Validar: `code` y `name` no vacíos (ya cubierto por el JSON Schema).
- Validar `type ∈ WAREHOUSE_TYPES` → si no, error `invalid_type` (el schema ya lo restringe;
  el WASM lo revalida por defensa).
- **Unicidad de `code` por hub**: el runtime lee `warehouses.list` (o un get-by-code); si ya
  existe un almacén con ese `code` (no borrado) → error `duplicate_code` (mensaje más limpio
  que el `IntegrityError` del índice `uq_mw_warehouse_hub_code`, que sigue siendo la red de
  seguridad).
- **Demote del default anterior**: si `is_default=true`, hay que poner `is_default=0` en
  cualquier almacén del hub que sea default actualmente, ANTES de insertar el nuevo con
  `is_default=1`. Son dos sentencias condicionales (UPDATE + INSERT) → no es Tier 0.
- Insertar el almacén nuevo (id, hub_id, code, name, type, address, is_default,
  owner_organization_ref, is_active=1) con el contrato de auditoría (`created_by/updated_by=
  :current_user_id`, `created_at/updated_at=:now`).
- Devolver `{id, code, name, type, is_default}`. Emitir `multi_warehouse.warehouse.created`.

## 2. `set_default_warehouse`  (command `multi_warehouse.warehouses.set_default`)
Origen: `MultiWarehouseService.set_default_warehouse`.
- Cargar el almacén `warehouse_id` (scope hub); si no existe → error `not_found`.
- **Demote batch**: poner `is_default=0` en TODOS los demás almacenes del hub que sean default
  (`id != warehouse_id`), luego `is_default=1` en el objetivo. Batch sobre N filas + un UPDATE
  → no es Tier 0 (requiere garantizar a-lo-sumo-un-default atómicamente).
- Devolver `{id, code, is_default}`. Emitir `multi_warehouse.warehouse.default_changed`.

## 3. `create_transfer`  (command `multi_warehouse.transfers.create`)
Origen: `MultiWarehouseService.create_transfer` + `WarehouseTransfer.generate_number`.
- Validar `lines` no vacía (cubierto por schema).
- Validar `source_warehouse_id != destination_warehouse_id` → error `same_warehouse`.
- Validar que ambos almacenes existen y pertenecen al hub (runtime los lee; el WASM revalida)
  → errores `source_not_found` / `destination_not_found`.
- Por cada línea: `product_ref` no vacío (error `missing_product`); `quantity_requested` > 0
  (error `invalid_line`); `lot_ref` opcional.
- **Numeración atómica** `WT-YYYYMMDD-NNNN` (ver pieza 7) → `transfer_number` único por hub+día.
- Insertar la cabecera (`status='draft'`, `created_date=hoy`, carrier/tracking_ref/notes) y una
  fila por línea (`quantity_dispatched=0`, `quantity_received=0`). Batch multi-fila → WASM.
- Devolver `{id, transfer_number, status, lines_count}`. Emitir `multi_warehouse.transfer.created`.

## 4. `dispatch_transfer`  (command `multi_warehouse.transfers.dispatch`)
Origen: `MultiWarehouseService.dispatch_transfer`.
- **Guarda de estado**: solo desde `draft` (si no → error `invalid_state`).
- `dispatched_lines = [{line_id, quantity_dispatched}, ...]`. Validar que cada `line_id`
  pertenece a este traslado (error `line_not_found`) y `quantity_dispatched >= 0`
  (error `invalid_line`). Las líneas no referenciadas se quedan en `quantity_dispatched=0`.
- Aplicar: por cada par, `UPDATE line SET quantity_dispatched=qty`; transicionar la cabecera a
  `status='in_transit'` y `dispatched_date=hoy`. Batch de N updates + transición → WASM.
- Devolver `{id, transfer_number, status, dispatched_date, lines_updated}`.
  Emitir `multi_warehouse.transfer.dispatched`.

## 5. `receive_transfer`  (command `multi_warehouse.transfers.receive`)
Origen: `MultiWarehouseService.receive_transfer`.
- **Guarda de estado**: solo desde `in_transit` (si no → error `invalid_state`).
- `received_lines = [{line_id, quantity_received}, ...]`. Misma validación que dispatch
  (`line_not_found`, `quantity_received >= 0`). Recepciones parciales permitidas
  (received < dispatched, no se fuerza igualdad).
- Aplicar: `UPDATE line SET quantity_received=qty`; transición a `status='received'`,
  `received_date=hoy`. Batch + transición → WASM.
- Devolver `{id, transfer_number, status, received_date, lines_updated}`.
  Emitir `multi_warehouse.transfer.received`.

## 6. `cancel_transfer` — YA EN TIER 0 (`commands/transfer_cancel.sql`)
Origen: `MultiWarehouseService.cancel_transfer`. La guarda (no `received`/`cancelled`) se
expresa en el `WHERE` y el append de `[CANCELLED] reason` a `notes` se hace con concat SQLite.
No necesita WASM. (Si en Postgres el `char(10)`/`||` difiere, considerar moverlo a WASM por
portabilidad — ver §14 portabilidad SQL del ARQUITECTURA.)

## 7. Generación atómica del nº de traslado (`generate_number`)
Origen: `WarehouseTransfer.generate_number`.
- Formato `WT-YYYYMMDD-NNNN`: prefijo con la fecha de hoy + secuencia de 4 dígitos que cuenta
  los traslados del hub emitidos ese mismo día.
- El legacy hace SELECT del último `transfer_number LIKE 'WT-YYYYMMDD-%'` ORDER BY desc + parse
  del sufijo, lo que tiene ventana de carrera (resuelta por el índice único `uq_mw_transfer_hub_number`
  + retry del caller). En hub-next debe resolverse como **counter UPSERT del runtime** (sin
  ventana SELECT→UPDATE), invocado por el handler; el WASM solo formatea `WT-{day}-{n:04d}`
  con el número devuelto.
