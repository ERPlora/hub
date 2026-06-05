# collections — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_collections/{models.py,services.py}`. En este módulo **todas**
las mutaciones llevan lógica que no cabe en una sola sentencia SQL (generación de referencia
atómica, aritmética de asignación, transiciones de estado, append de rastro en `notes`), por
lo que **no hay `commands/*.sql`**: cada comando se resuelve con el handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`) declarado en `module.json`.

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar/soft-delete) que el
> runtime valida y persiste en una transacción. Todos los importes se tratan como `Decimal`
> con `quantize(0.01)` (o enteros de céntimos). El runtime inyecta `:new_id`, `:hub_id`,
> `:current_user_id`, `:now` al materializar cada intención.

Tablas que OWNea el módulo (única fuente de escritura): `collections_collection`,
`collections_allocation`, `collections_counter`. El módulo NO referencia tablas de
invoice/customers: `invoice_ref` y `payer_name` son texto libre (independencia de módulos).

## Métodos / choices (de models.py)
- `COLLECTION_METHODS = (transfer, card, cash, sepa, other)` — validado por el schema (enum).
- `COLLECTION_STATUSES = (pending, allocated, refunded, cancelled)`.

---

## 1. `create_collection`  (command `collections.collections.create`)
Origen: `CollectionService.create_collection`.
- Validar: `payer_name` no vacío; `method` ∈ COLLECTION_METHODS (ya cubierto por el enum del
  schema, revalidar defensivamente); `collection_date` ISO `YYYY-MM-DD`; `amount` parseable a
  Decimal y `> 0` (rechazar `<= 0` con código `invalid_amount`).
- Generar `reference` atómica → ver pieza 6 (counter). Formato `COL-YYYYMMDD-NNNN`.
- Emitir intención de INSERT en `collections_collection` con `status='pending'`,
  `currency` (default `EUR`), `payer_iban`/`concept`/`notes` (default `''`).
- Devolver `{id, reference, amount, currency, status}` y emitir evento `collections.collection.created`.

## 2. `allocate_to_invoice`  (command `collections.collections.allocate`)
Origen: `CollectionService.allocate_to_invoice`.
- Validar: `invoice_ref` no vacío; `amount_allocated` Decimal `> 0`.
- Leer (runtime) el cobro `collection_id` (scope hub_id, is_deleted=0). Si no existe → error.
- Guarda de estado: **solo** si `status == 'pending'` (si no → error `invalid_state`).
- Leer (runtime) las asignaciones vivas del cobro; `already = Σ amount_allocated` con
  `quantize(0.01)`.
- Invariant: `already + amount_allocated` **no** puede superar `collection.amount`. Si lo
  supera → error `over_allocated` devolviendo `remaining = amount - already`.
- Intenciones: INSERT en `collections_allocation` (`allocated_at = :now`); si
  `already + amount_allocated == amount` (con `quantize(0.01)`) → UPDATE del cobro a
  `status='allocated'`.
- Devolver `{id, collection_id, invoice_ref, amount_allocated, collection_status,
  total_allocated, unallocated_amount}`; emitir `collections.allocation.created`.

## 3. `unallocate`  (command `collections.collections.unallocate`)
Origen: `CollectionService.unallocate`.
- Leer la asignación `allocation_id` (scope hub_id). Si no existe → error.
- Leer su cobro padre. Guarda: si el cobro está `refunded`/`cancelled` → error `invalid_state`
  (no se puede tocar el reparto de un cobro cerrado).
- Intenciones: **soft-delete** de la asignación (`is_deleted=1`, `deleted_at=:now`).
- Recalcular `new_total = Σ amount_allocated` de las asignaciones vivas restantes. Si el cobro
  estaba `allocated` y `new_total != amount` → UPDATE del cobro a `status='pending'`
  (vuelve a aceptar repartos).
- Devolver `{allocation_id, collection_id, collection_status, total_allocated,
  unallocated_amount}`; emitir `collections.allocation.removed`.
- Nota: el legacy hace `session.delete` (borrado físico, CASCADE). En hub-next el contrato de
  fila exige soft-delete → se usa `is_deleted=1`; las queries ya filtran `is_deleted=0`.

## 4. `refund_collection`  (command `collections.collections.refund`)
Origen: `CollectionService.refund_collection`.
- Leer el cobro. Guardas: si ya `refunded` → error `already_refunded`; si `cancelled` →
  error `cancelled_locked` (no se reembolsa un cancelado).
- Intención: UPDATE `status='refunded'`. Si `reason` no vacío, **append** al rastro de
  `notes`: `notes = (notes + "\n[REFUNDED] " + reason).strip()` (capacidad de composición de
  texto del host; el WASM compone el nuevo `notes`).
- Devolver `{id, reference, status}`; emitir `collections.collection.refunded`.

## 5. `cancel_collection`  (command `collections.collections.cancel`)
Origen: `CollectionService.cancel_collection`.
- Leer el cobro. Guardas: si ya `cancelled` → error `already_cancelled`; si `refunded` →
  error `refunded_locked` (emitir rectificación contable en su lugar).
- Intención: UPDATE `status='cancelled'`. Si `reason` no vacío, **append** a `notes`:
  `notes = (notes + "\n[CANCELLED] " + reason).strip()`.
- Devolver `{id, reference, status}`; emitir `collections.collection.cancelled`.

---

## 6. Contador atómico de referencia (`generate_collection_reference`)
Origen: `CollectionCounter` + `generate_collection_reference` (UPSERT
`INSERT ... ON CONFLICT(hub_id, day) DO UPDATE SET last_number = last_number + 1 RETURNING`).
- Formato `COL-YYYYMMDD-NNNN` (`NNNN` = secuencia por `hub+día`, 4 dígitos, cero-padded).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres — se resuelve como
  **capacidad del runtime** (counter UPSERT sobre `collections_counter`) invocada por el
  handler; el WASM solo formatea `COL-{day}-{n:04d}` con el número devuelto.
- Guard adicional: el índice único `uq_collection_hub_reference (hub_id, reference)` protege
  contra duplicados aunque dos cobros se creen en paralelo.

## 7. Cálculo de totales por cobro (consumido por queries/UI)
Origen: `Collection.total_allocated` / `unallocated_amount`.
- `total_allocated = quantize(Σ allocation.amount_allocated, 0.01)` sobre asignaciones vivas.
- `unallocated_amount = quantize(amount - total_allocated, 0.01)`.
- Lo necesitan `allocate_to_invoice` (piezas 2) y `unallocate` (pieza 3) para decidir las
  transiciones de estado, y la UI para mostrar el saldo pendiente del cobro. La cabecera
  (`collections.collections.get`) + las filas (`collections.allocations.list`) bastan para
  que el SDK/UI calcule estos totales en cliente; el handler los recalcula server-side al
  mutar para los invariants.
