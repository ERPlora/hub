# glovo — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_glovo/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
`stores.create`, `stores.update_status`, `orders.update_status`, `menu_syncs.start`.

Lo que sigue es lógica de idempotencia / secuencia atómica / upsert condicional / derivación
de estado que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos a
> ejecutar) que el runtime valida y persiste en una transacción. Todos los importes son
> decimales con `quantize(0.01)`. El reloj (`now`) y la generación de UUID son capacidades
> del host inyectadas por el runtime.

## 1. `import_order`  (command `glovo.orders.import`)
Origen: `GlovoService.import_order` + `generate_order_number` (models.py).
- **Validar**: `order_code` no vacío; `items` es lista (no `null`).
- **Resolver tienda**: el runtime lee `glovo_store` por `id = store_id_internal` (+ `hub_id`,
  `is_deleted=0`). Si no existe → error `store_not_found`.
- **Idempotencia** (clave del comando): buscar `glovo_order` por `(hub_id, order_code)`.
  - Si existe → devolver `{id, order_code, order_number, status, already_existed: true}`
    **sin** insertar ni rotar el `order_number`. El índice único
    `ix_glovo_order_hub_order_code` es la guarda adicional.
- **Parseo/normalización**:
  - `total_amount` → Decimal `quantize(0.01)`; valor inválido → error `invalid_amount`.
  - `created_at_glovo` → ISO `YYYY-MM-DDTHH:MM:SS` normalizado a UTC naive, o NULL si vacío;
    inválido → error `invalid_date`.
  - `items` / `delivery_address` se serializan a JSON (texto) para las columnas TEXT.
- **Número de pedido atómico**: ver pieza 4 (counter). Formato `GLO-YYYYMMDD-NNNN`.
- **Persistir** la nueva fila `glovo_order` (status `new`, `currency` default `EUR`) y devolver
  `{id, order_code, order_number, status: "new", already_existed: false}`.
- Emite `glovo.order.imported` (declarado en `module.json`).

## 2. `complete_menu_sync`  (command `glovo.menu_syncs.complete`)
Origen: `GlovoService.complete_menu_sync`.
- **Resolver** la fila `glovo_menu_sync` por `(id = sync_id, hub_id, is_deleted=0)`; no existe →
  error `not_found`.
- **Guarda de estado**: solo si `status == 'running'`; en otro caso → error `invalid_state`.
- **Derivar nuevo estado**: `failed` si `error_log` no vacío, si no `completed`.
- Actualizar la fila: `status`, `items_synced = int(items_synced)`, `error_log`,
  `completed_at = now`.
- **Efecto lateral cross-fila (mismo módulo)**: si `completed`, sellar el `last_sync_at` de la
  tienda padre (`glovo_store.id = sync.store_id`) con `completed_at`. Son dos UPDATEs en la
  misma transacción → por eso es WASM y no un único UPDATE.
- Devolver `{id, status, items_synced}`. Emite `glovo.menu_sync.completed`.

## 3. `sync_product`  (command `glovo.products.sync`)
Origen: `GlovoService.sync_product`.
- Upsert idempotente por `(hub_id, store_id, glovo_product_id)`:
  - **Resolver tienda** por `store_id_internal` (igual que pieza 1); no existe → `store_not_found`.
  - Validar `glovo_product_id` y `name` no vacíos; `price` → Decimal `quantize(0.01)` (inválido →
    `invalid_price`).
  - Buscar `glovo_product` existente por `(store_id, glovo_product_id)` dentro del hub.
    - **No existe** → INSERT (`is_available`, `local_product_ref`, `last_synced_at = now`),
      `created = true`.
    - **Existe** → UPDATE de `local_product_ref`, `name`, `price`, `is_available`,
      `last_synced_at = now`, `updated_by/updated_at`; `created = false`.
- Devolver `{id, glovo_product_id, local_product_ref, created}`. Emite `glovo.product.synced`.
- Es un upsert (SELECT→INSERT|UPDATE condicional) → no cabe en una sola sentencia portable a
  SQLite+Postgres con la rama de retorno `created`; va a WASM.

## 4. Contador atómico de nº de pedido (`generate_order_number`)
Origen: `generate_order_number` + `GlovoOrderCounter` (models.py).
- UPSERT atómico sobre `glovo_order_counter` por `(hub_id, day)` con
  `last_number = last_number + 1` y `RETURNING last_number` — **sin** ventana SELECT→UPDATE
  (atómico en SQLite y Postgres). `day = YYYYMMDD` (UTC) del reloj del host.
- En hub-next se resuelve como **capacidad del runtime** (counter UPSERT) invocada por el
  handler; el WASM solo formatea `GLO-{day}-{n:04d}` con el número devuelto.
- Guarda adicional: índice único `ix_glovo_order_hub_order_number`.

## 5. `get_store_metrics` (query analítica — pendiente de decisión Tier)
Origen: `GlovoService.get_store_metrics`. **No** migrada como query SQL declarativa porque
agrega varias fuentes y formas:
- Pedidos de la tienda en los últimos `period_days` (ventana de fechas sobre `created_at`).
- `orders_by_status`: conteo por cada uno de los 6 estados (incluye ceros para estados sin
  pedidos — requiere materializar el enum completo, no un `GROUP BY` simple).
- `revenue_delivered`: suma de `total_amount` solo de pedidos `delivered`, `quantize(0.01)`.
- `active_products`: conteo de `glovo_product` con `is_available=1` de la tienda.
- `last_menu_sync`: la sync más reciente serializada.
- Devuelve además `currency` (del primer pedido) y `period_days`.
Candidata a un handler WASM de solo-lectura (Tier 2) o a varias queries Tier 0 + agregación en
el WC. Decisión pendiente; no se ha añadido entrada de query ni de nav para evitar paths
colgantes hasta implementarla.
