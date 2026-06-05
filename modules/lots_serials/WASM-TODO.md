# lots_serials — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_lots_serials/{models.py,services.py}`. El CRUD plano y las
transiciones de estado con guard simple (números de serie) ya están en SQL declarativo
Tier 0 (`commands/serial_*.sql`). Lo que sigue es lógica de cálculo / multi-sentencia /
auto-transición de estado que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. Las cantidades se manejan como decimales con
> `quantize(0.001)` (la BD usa `NUMERIC(15,3)` en el legacy).

## 1. `create_lot`  (command `lots_serials.lots.create`)
Origen: `LotService.create_lot`.
- Validar: `lot_number` no vacío; `product_ref` no vacío.
- Parsear/validar `quantity_initial` como decimal `>= 0` (acepta string o número) → error
  `invalid_quantity` si negativo o no parseable.
- Parsear `manufactured_date` / `expiry_date` (ISO `YYYY-MM-DD` o vacío/NULL) → error
  `invalid_date`.
- Guard de duplicado: si ya existe un `lots_serials_lot` con ese `lot_number` en el hub →
  error `duplicate_lot` (además del índice único `uq_lot_hub_number`).
- Intenciones a devolver (multi-sentencia, en transacción):
  1. INSERT del lote: `quantity_initial = quantity_current = qty`, `status = 'active'`.
  2. **Solo si `qty > 0`**: INSERT de un movimiento de apertura en `lots_serials_movement`
     con `movement_type = 'intake'`, `quantity_delta = qty`, `reference = 'opening'`,
     `occurred_at = :now`. Este movimiento condicional es lo que impide expresarlo como un
     único command SQL.
- Emitir `lots_serials.lot.created`. Devolver `{id, lot_number, product_ref,
  quantity_initial, quantity_current, status}`.

## 2. `record_movement`  (command `lots_serials.lots.record_movement`)
Origen: `LotService.record_movement`.
- Validar `movement_type ∈ {intake, consume, adjust, expire, recall}` → error
  `invalid_movement_type`.
- Leer el lote por `lot_id` (runtime) → error `not_found` si no existe.
- Parsear `quantity_delta` como decimal **firmado** (positivo intake/adjust+, negativo
  consume/expire/recall) → error `invalid_quantity`.
- Calcular `new_qty = lot.quantity_current + delta`.
  - Si `new_qty < 0` → error `negative_quantity` (no se permite dejar el lote en negativo).
- Intenciones (en transacción):
  1. INSERT del movimiento en `lots_serials_movement` (`quantity_delta = delta`,
     `reference`, `notes`, `occurred_at = :now`).
  2. UPDATE del lote: `quantity_current = new_qty`.
  3. **Auto-transición de estado**: si `lot.status == 'active'` y `new_qty == 0` →
     `status = 'depleted'`. NO tocar lotes `recalled`/`expired`/ya-`depleted`.
- Emitir `lots_serials.movement.recorded`. Devolver `{id, lot_id, movement_type,
  quantity_delta, quantity_current, status}`.

## 3. `mark_recalled`  (command `lots_serials.lots.mark_recalled`)
Origen: `LotService.mark_recalled`.
- Leer el lote por `lot_id` → error `not_found`.
- Guard: si `lot.status == 'recalled'` → error `already_recalled`.
- `quantity_current` se deja **intacto** (las unidades recalled siguen en libros pero
  marcadas como inutilizables; quien quiera además darlas de baja llama después a
  `record_movement` con `movement_type = 'recall'`).
- Intenciones (en transacción):
  1. UPDATE del lote: `status = 'recalled'`. Si `reason` no vacío, **append** a `notes`:
     `notes = (notes + "\n[RECALLED] " + reason).strip()` — composición de texto que
     requiere leer el `notes` actual, por eso va a WASM y no a un UPDATE plano.
  2. INSERT de un movimiento `recall` con `quantity_delta = 0`, `reference = 'recall'`,
     `notes = reason`, `occurred_at = :now`.
- Emitir `lots_serials.lot.recalled`. Devolver `{id, lot_number, status}`.

## Notas sobre lo que NO va a WASM (queda Tier 0 / runtime)

- `register_serial` → `commands/serial_register.sql`. La validación opcional de que el
  `lot_id` referenciado existe la hace el runtime antes de ejecutar el INSERT; el resto es
  un INSERT plano. (Guard de duplicado por índice único `uq_serial_hub_serial`.)
- `mark_serial_sold` / `mark_serial_returned` → `commands/serial_mark_sold.sql` /
  `serial_mark_returned.sql`. El guard de estado (`in_stock → sold`, `sold → returned`) se
  expresa en el `WHERE ... AND status = '<estado>'`; si no se actualiza ninguna fila, el
  runtime devuelve el error `invalid_state`. No requiere cálculo.
- `list_lots` / `get_lot` (+ sus movimientos) / `list_serials` → queries declarativas
  (`queries/*.sql`).
- `check_expiring_lots` → `queries/lots_expiring.sql`. El único matiz es calcular
  `horizon = hoy + within_days`; eso lo hace el runtime (capacidad de reloj) y se pasa
  como bind `:horizon`. No necesita WASM.
