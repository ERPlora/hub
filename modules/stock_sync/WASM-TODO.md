# stock_sync — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_stock_sync/{models.py,services.py}`. El CRUD plano
(alta de canal, alta de item) ya está en SQL declarativo Tier 0 (`commands/channel_create.sql`,
`commands/sync_item_record.sql`). Lo que sigue es lógica con guardas de estado, batch
multi-fila, numeración atómica y short-circuit que **no** cabe en una sola sentencia SQL y
debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas leídas por el
> runtime, valida y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> persiste en una transacción. Las cantidades son decimales `Numeric(15,3)`; usar el mismo
> tipo (`quantize(0.001)`) para comparaciones de igualdad.

## Capacidad de runtime compartida — contador atómico de run_number
Origen: `StockSyncCounter` + `generate_run_number` (UPSERT `INSERT ... ON CONFLICT (hub_id, day)
DO UPDATE SET last_number = last_number + 1 RETURNING last_number`).
- Formato `SS-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- En hub-next es una **capacidad del runtime** (counter UPSERT, no una tabla de negocio
  expuesta): el handler la invoca y solo formatea `SS-{day}-{n:04d}` con el número devuelto.
- La tabla `stock_sync_counter` legacy **no** se materializa en `001_init.sql`.

## 1. `start_sync`  (command `stock_sync.runs.start`)
Origen: `StockSyncService.start_sync`.
- Validar: `source_channel_id != target_channel_id` (si no → error `same_channel`).
- Resolver y validar que ambos canales existen y pertenecen al hub (si no → error
  `not_found`, `Source channel not found` / `Target channel not found`).
- Generar `run_number` atómico (capacidad de runtime, arriba).
- Insertar la cabecera del run: `status='running'`, `started_at=:now`, `items_synced=0`,
  `conflicts_count=0`, `error_log=''`.
- Por cada elemento de `products[]` con `product_ref` no vacío: insertar un `stock_sync_item`
  con `source_quantity`/`target_quantity` (parseo a decimal, default 0) y `action` (si no está
  en `push|pull|skip|conflict` → cae a `push`). Saltar los que no tengan `product_ref`.
- Devolver `{id, run_number, status, items_count}`.
- Operación multi-fila (cabecera + N items) en una sola transacción → WASM (intenciones:
  1 insert de run + N inserts de item).

## 2. `complete_sync`  (command `stock_sync.runs.complete`)
Origen: `StockSyncService.complete_sync`.
- Leer el run; si no existe → error `not_found` (`Sync run not found`).
- Guarda de estado: **solo** si `status == 'running'` (si no → error `invalid_state`,
  `Only running syncs can be completed`).
- Actualizar `completed_at=:now`, `items_synced`, `conflicts_count`.
- Si `error_log` viene con contenido → `status='failed'` y guardar `error_log`.
  En caso contrario → `status='completed'`.
- **Si quedó `completed`**: bump de `last_sync_at=:now` en **ambos** canales (origen y destino)
  — actualización cross-fila al run pero dentro del propio módulo (tabla `stock_sync_channel`).
- Devolver `{id, run_number, status, items_synced, conflicts_count}`.
- Guarda de estado + actualización condicional de 2 filas extra → WASM.

## 3. `detect_conflict`  (command `stock_sync.conflicts.detect`)
Origen: `StockSyncService.detect_conflict`.
- Validar `product_ref` no vacío (si no → error `missing_product`).
- Resolver y validar ambos canales (existen y son del hub; si no → `not_found`).
- Parsear `source_qty`/`target_qty` a decimal (error `invalid_quantity` si no parsea).
- **Short-circuit**: si `source_qty == target_qty` → NO insertar nada; devolver
  `{conflict:false, message:'quantities match'}`.
- Si difieren → insertar `stock_sync_conflict` con `status='open'`, `detected_at=:now`,
  `resolution_strategy=''`, `resolved_at=NULL`.
- Devolver `{id, conflict:true, product_ref, source_quantity, target_quantity, status}`.
- La rama "no insertar si son iguales" es una decisión condicional → WASM (devuelve 0 o 1
  intención de insert).

## 4. `resolve_conflict`  (command `stock_sync.conflicts.resolve`)
Origen: `StockSyncService.resolve_conflict`.
- Validar `strategy` ∈ `use_source|use_target|manual|ignore` (el JSON Schema ya lo acota).
- Leer el conflicto; si no existe → error `not_found` (`Conflict not found`).
- Guarda de estado: **solo** si `status == 'open'` (si no → error `invalid_state`).
- Mapeo de estado final: `status = 'ignored'` si `strategy == 'ignore'`, en caso contrario
  `status = 'resolved'`. Guardar `resolution_strategy=strategy`, `resolved_at=:now`,
  `updated_by=:current_user_id`, `updated_at=:now`.
- Devolver `{id, status, resolution_strategy, resolved_at}`.
- NOTA: el legacy **no** aplica la cantidad ganadora a ningún stock real (no hay efecto sobre
  inventario; solo cierra el conflicto). Si en el futuro se quiere propagar la cantidad
  elegida al módulo `inventory`, hacerlo vía **evento** (`stock_sync.conflict.resolved` con
  payload `{product_ref, winning_quantity, channel}`), nunca tocando tablas de `inventory`.
- Guarda de estado + mapeo condicional ignore→ignored / *→resolved → WASM.

## Eventos emitidos (ver module.json `emit`)
- `stock_sync.channel.created` — alta de canal (Tier 0).
- `stock_sync.item.recorded` — alta de item en run en curso (Tier 0).
- `stock_sync.run.started` / `stock_sync.run.completed` — ciclo de vida del run (WASM).
- `stock_sync.conflict.detected` / `stock_sync.conflict.resolved` — ciclo de vida del
  conflicto (WASM). Punto de extensión cross-módulo hacia `inventory` sin acoplar tablas.
