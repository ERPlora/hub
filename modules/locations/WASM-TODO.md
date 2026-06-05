# locations — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_locations/{models.py,services.py}`. El CRUD plano (almacenes,
zonas, bins) y los toggles simples (block/unblock) ya están en SQL declarativo Tier 0
(`commands/*.sql`). Lo que sigue es la lógica de **upsert por clave compuesta** y **batch**
que no cabe en una sola sentencia SQL portable (SQLite↔Postgres) y que necesita devolver
metadatos por fila (`created`), por lo que se convierte en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el runtime
> haya leído (vía las queries públicas del módulo) y devuelve *intenciones* (filas a
> insertar/actualizar) que el runtime valida y persiste en una transacción. Las cantidades
> son decimales `NUMERIC(15,3)` → cuantizar a 3 decimales.

## Binds que el runtime inyecta a todo handler
`:hub_id`, `:current_user_id`, `:now` (ISO-8601 UTC), `:new_id` (UUID por cada fila nueva).

---

## 1. `update_stock_position`  (command `locations.stock.update_position`)
Origen: `LocationService.update_stock_position`.

Upsert de UNA posición de stock por la clave compuesta `(hub_id, bin_id, product_ref, lot_ref)`.

- **Payload**: `{ bin_id, product_ref, quantity, lot_ref? }` (validado por `schemas/stock_update.json`).
  `lot_ref` ausente o null → `""` (la clave única colapsa las posiciones sin lote a una fila).
- **Guard de existencia**: el runtime resuelve que `bin_id` existe y pertenece al hub leyendo
  `locations.bins.list` (filtrado por zona/almacén) o una lectura puntual del bin antes de
  invocar; el WASM **no** consulta otra tabla por su cuenta. Si no existe → error `bin_not_found`.
- **Lectura previa**: el runtime pasa al handler la posición actual (si la hay) consultada con
  `locations.stock.at_bin` filtrada por `product_ref`+`lot_ref`.
- **Lógica**:
  - Si no existe la posición → intención `_insert_position` con
    `{ id: :new_id, hub_id, bin_id, product_ref, lot_ref, quantity, last_count_at: :now }`
    y `created = true`.
  - Si existe → intención `_update_position` con `{ id, quantity, last_count_at: :now }`
    y `created = false` (NO se reescriben product_ref/lot_ref/bin_id).
- **Devuelve**: `{ id, bin_id, product_ref, lot_ref, quantity, created }`.
- **Emite**: `locations.stock.counted`.

## 2. `count_bin`  (command `locations.stock.count_bin`)
Origen: `LocationService.count_bin`.

Upsert **en lote** de N posiciones desde un recuento físico de un bin. Es la misma lógica de
upsert de la pieza 1 aplicada a cada entrada de `counts`, dentro de **una sola transacción**
(o todo o nada), devolviendo la lista de resultados con su flag `created`.

- **Payload**: `{ bin_id, counts: [{ product_ref, quantity, lot_ref? }, ...] }`
  (validado por `schemas/count_bin.json`; `counts` no vacío garantizado por `minItems: 1`).
- **Guard de existencia** del bin: igual que la pieza 1 (`bin_not_found` si no existe).
- **Lectura previa**: el runtime pasa todas las posiciones actuales del bin
  (`locations.stock.at_bin`) para que el handler decida insert vs update por
  `(product_ref, lot_ref)` sin más lecturas.
- **Lógica**: por cada entrada de `counts`, aplicar el upsert de la pieza 1
  (`last_count_at = :now` en todas). Cuantizar `quantity` a 3 decimales.
- **Devuelve**: `{ bin_id, counted: N, positions: [{ id, product_ref, lot_ref, quantity, created }, ...] }`.
- **Emite**: `locations.stock.counted` (un único evento por lote).
- **Por qué WASM y no SQL**: el upsert por clave compuesta con metadatos `created` por fila +
  la naturaleza de lote (devolver la lista completa de resultados) no es expresable como una
  sola sentencia portable SQLite/Postgres. (En Postgres sería `INSERT ... ON CONFLICT DO UPDATE
  RETURNING`, pero SQLite no devuelve si fue insert o update; de ahí el handler.)

---

## Notas sobre invariants ya resueltos en Tier 0 (no van a WASM)
- **Único almacén por defecto por hub** (`create_warehouse` con `is_default`): resuelto en
  `commands/warehouse_create.sql` con una UPDATE guardada por bind (`:is_default = 1`) seguida
  del INSERT, ambas en la misma transacción. No requiere handler.
- **Unicidad de códigos** (warehouse.code por hub; zone.code por (hub,warehouse);
  bin.code por (hub,warehouse)): garantizada por los índices únicos de la migración; el runtime
  traduce la violación de constraint a error `duplicate_code`.
- **Validación de `zone_type`**: enum en `schemas/zone_create.json`.
- **Guards de block/unblock** ("ya bloqueado" / "no estaba bloqueado"): resueltos por el
  `WHERE is_blocked = 0/1` de los UPDATE (no tocan filas si el estado ya es el deseado).
- **Denormalización de `warehouse_id` en el bin**: el runtime lo resuelve leyendo la zona
  (`locations.zones.list`) antes de ejecutar `bin_create.sql` y lo pasa como `:warehouse_id`.
  El WC nunca lo deriva tocando otra tabla.
