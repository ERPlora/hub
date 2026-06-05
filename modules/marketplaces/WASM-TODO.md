# marketplaces — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_marketplaces/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
`connection_create`, `connection_deactivate`, `mapping_create`, `order_fulfill`, `sync_start`.
Lo que sigue es lógica de atomicidad / idempotencia / mutación multi-tabla / enmascarado que
**no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos
> internos `_insert_*` / `_set_*`, invocaciones a la capacidad de counter UPSERT del host)
> que el runtime valida y persiste en una transacción. Importes como decimales con
> `quantize(0.01)`.

## 1. `import_order`  (command `marketplaces.orders.import`, handler WASM)
Origen: `MarketplaceService.import_order` + `generate_marketplace_order_number`.
Es WASM (no Tier 0) por tres motivos combinados: idempotencia con lookup previo, generación
atómica del número de pedido vía counter UPSERT, y validación de importe.
- Validar: `external_order_id` no vacío, `customer_name` no vacío, `items` lista no vacía
  (el JSON Schema ya cubre lo básico; la regla de negocio se reafirma aquí).
- **Idempotencia**: el runtime lee si ya existe un `marketplaces_order` con
  `(connection_id, external_order_id)` para este hub. Si existe → error `duplicate_order`
  (no se inserta nada). El índice único `ix_mp_order_connection_external` es el respaldo final.
- Validar/parsear `total_amount` (string decimal). Si no parsea → error `invalid_amount`.
- **Generar `order_number` atómico** → ver pieza 4 (counter). Formato `MP-YYYYMMDD-NNNN`.
- Insertar el `marketplaces_order` con `status='imported'`, `currency='EUR'`,
  `order_date = now`, `shipping_address={}`, `items` = payload verbatim (JSON).
- Verificar que la conexión existe y pertenece al hub (el runtime resuelve la FK).
- Emite `marketplaces.order.imported`.
- Devolver `{id, order_number, external_order_id, status, total_amount, items_count}`.

## 2. `complete_sync`  (command `marketplaces.syncs.complete`, handler WASM)
Origen: `MarketplaceService.complete_sync`.
Es WASM porque muta **dos tablas** en la misma transacción (el SyncRun y el snapshot de la
conexión padre) con una guarda de estado — no es un solo UPDATE.
- Guarda de estado: **solo** si el SyncRun está en `running` (si no → error `invalid_state`).
- Calcular `final_status`: `'failed'` si `error_log` no vacío, si no `'completed'`.
- Mutación 1 — `marketplaces_sync_run`: `status=final_status`, `completed_at=now`,
  `items_synced`, `items_failed`, `error_log`, `updated_by/updated_at`.
- Mutación 2 — `marketplaces_connection` (la conexión padre del run):
  `last_sync_at=now`, `last_sync_status=final_status`, `updated_by/updated_at`.
  El runtime resuelve la conexión a partir de `run.connection_id` (misma tabla del módulo,
  NO cross-módulo).
- Emite `marketplaces.sync.completed`.
- Devolver `{id, status, items_synced, items_failed}`.

## 3. Enmascarado de credenciales (`_mask_credentials`)
Origen: `MarketplaceService._mask_credentials` + `_serialize_connection`.
La columna `marketplaces_connection.credentials` (JSON) guarda claves/secretos/tokens OAuth.
La query `marketplaces.connections.list` los devuelve crudos del Tier 0 SQL; el enmascarado
debe aplicarse antes de exponerlos al cliente.
- Recorrer recursivamente el JSON de credentials: todo valor string no vacío → `"***"`;
  los dicts anidados se recorren igual; otros tipos se conservan. Las **claves** se conservan
  intactas para que el cliente vea qué slots están poblados.
- Opciones de implementación (decidir en build):
  (a) handler WASM `mask_connection` que post-procesa la fila antes de devolverla, o
  (b) capacidad Tier 1 del host que enmascara campos marcados como sensibles.
- Hasta que se cablee, la UI de `erp-marketplaces-connections` **no** pide ni muestra el
  campo `credentials` (solo metadatos: code/name/platform/region/estado de sync).

## 4. Contador atómico de nº de pedido (`generate_marketplace_order_number`)
Origen: `MarketplaceOrderCounter` + `generate_marketplace_order_number` (UPSERT
`INSERT ... ON CONFLICT (hub_id, day) DO UPDATE SET last_number = last_number + 1 RETURNING`).
Formato `MP-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres — mismo patrón que
  `m_credit_notes` / `m_collections` / quotes.
- En hub-next se resuelve como capacidad del runtime (counter UPSERT sobre
  `marketplaces_order_counter`) invocada por el handler de `import_order`; el WASM solo
  formatea `MP-{day}-{n:04d}` con el número devuelto.

## 5. Conectores reales de marketplace (fuera de alcance del módulo declarativo)
Origen: docstring de `import_order` ("placeholder — no real connector yet").
El legacy NO trae integración real con Amazon/eBay/etc.; `import_order` y los SyncRun son
bookkeeping local. La sincronización real (llamar a APIs externas, paginar pedidos, empujar
precios/stock) requeriría salida de red mediada (`http.fetch`, Tier 1) y queda como trabajo
futuro — no se implementa aquí. Cross-módulo: el ajuste de stock/precios del catálogo local
debe ir por **comandos/eventos públicos** de inventory/pricing, nunca tocando sus tablas.
