# purchase_orders — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_purchase_orders/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`:
`order_confirm`, `order_receive`, `order_cancel`, `supplier_create`). Lo que sigue es
lógica de cálculo / orquestación atómica multi-fila que **no** cabe en una sola sentencia
SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos
> internos `_bump_counter` / `_insert_order` / `_insert_line` a ejecutar) que el runtime
> valida y persiste en una transacción. Todos los importes son decimales con
> `quantize(0.01)` (`line_total = quantity * unit_price`, `total_amount = Σ line_total`).

## 1. `create_order`  (command `purchase_orders.orders.create`)
Origen: `PurchaseOrderService.create_order` + `PurchaseOrderLine.calculate_line_total` +
`PurchaseOrder.calculate_total` + `models.generate_order_number`.

Único command con `handler: {type: wasm, function: create_order}` en `module.json`. Orquesta
una operación atómica que toca tres tablas (counter, cabecera, N líneas) y por eso no es un
solo INSERT. Los tres comandos internos `_bump_counter` / `_insert_order` / `_insert_line`
(declarados en `module.json` como SQL Tier 0 privados, prefijo `_`) son las *intenciones* que
el handler emite; el runtime los ejecuta dentro de una sola transacción.

### Lógica no-CRUD que hace el handler
- **Validación de payload** (más allá del JSON Schema `schemas/create_order.json`):
  - `lines` lista no vacía (si vacía → error `empty_lines`).
  - Por cada línea: `product_name` no vacío tras `trim` (→ `invalid_line`); `quantity > 0`
    (→ `invalid_line`); `unit_price >= 0` (→ `invalid_line`).
  - `expected_date`: si no vacío, parsear ISO 8601; inválido → `invalid_expected_date`;
    vacío → NULL.
- **Validación de proveedor** (requiere lectura previa del runtime, no la hace el WASM):
  el supplier debe existir (→ `supplier_not_found`) y estar activo `is_active=1`
  (→ `supplier_inactive`). El runtime lee la fila del supplier y se la pasa al handler, o
  el handler la solicita como dato de entrada; el WASM solo decide sobre el flag, no consulta.
- **Número de pedido atómico** (`generate_order_number`, formato `PO-YYYYMMDD-NNNN`):
  el handler calcula `:day` (YYYYMMDD del `:now` del host) y emite `_bump_counter`; el
  runtime ejecuta el UPSERT (`INSERT ... ON CONFLICT (hub_id, day) DO UPDATE
  last_number = last_number + 1`) y devuelve `last_number`; el WASM formatea
  `PO-{day}-{n:04d}`. Atómico sin ventana SELECT→UPDATE en SQLite y Postgres.
- **Cálculo de `line_total` por línea**: `line_total = quantize(quantity * unit_price, 0.01)`.
  No hay descuentos ni impuestos en PO (a diferencia de quotes) — multiplicación directa.
- **Cálculo de `total_amount`**: `total_amount = Σ line_total` sobre todas las líneas.
- **Emisión de intenciones** (ejecutadas por el runtime en orden, una transacción):
  1. `_bump_counter`  binds: `:day`  (runtime inyecta `:new_id`, `:hub_id`).
  2. `_insert_order`  binds: `:supplier_id`, `:order_number`, `:expected_date` (o NULL),
     `:total_amount`, `:notes`  (runtime inyecta `:new_id`, `:hub_id`, `:current_user_id`,
     `:now`; status fijado a `'draft'`, `order_date = :now`).
  3. `_insert_line` × N  binds por línea: `:purchase_order_id` (= id de la cabecera recién
     creada), `:product_name`, `:quantity`, `:unit_price`, `:line_total`  (runtime inyecta
     `:new_id`, `:hub_id`, `:current_user_id`, `:now`).
- **Retorno** del command:
  `{id, order_number, status: "draft", supplier_id, total_amount, lines_count, created: true}`.
- **Evento**: el runtime emite `purchase_orders.order.created` (declarado en `module.json`).

### Binds / payload que necesitará
- Payload de entrada (validado contra `schemas/create_order.json`):
  `supplier_id`, `lines: [{product_name, quantity, unit_price}]`, `expected_date`, `notes`.
- Datos leídos por el host y pasados al handler: fila del supplier (`is_active`), `:now`
  (reloj del host), y el `last_number` devuelto por `_bump_counter`.

## 2. Alta de stock en `inventory` tras recibir (integración cross-module)
Origen: `PurchaseOrderService.receive_order` (hoy en `commands/order_receive.sql`, solo hace
la transición `confirmed -> received`; ver nota en ese SQL).

Hoy `order_receive` es Tier 0 (un UPDATE con guarda de estado). El alta de stock en el
módulo `inventory` al recibir un pedido **no** está implementada en hub-next y es lógica de
integración, no CRUD. NO se resuelve con imports — `purchase_orders` y `inventory` se
comunican por **contrato de eventos** (`module.json` ya declara `depends_on: ["inventory"]`
y `emit: ["purchase_orders.order.received"]`).

### Lógica de integración a implementar
- Al recibir (`confirmed -> received`), por cada línea del pedido hay que incrementar el
  stock del producto correspondiente en `inventory`.
- Opción de diseño recomendada (coherente con la regla cross-module = contratos, no imports):
  el runtime emite `purchase_orders.order.received` con el payload de las líneas recibidas
  `{order_id, order_number, supplier_id, lines: [{product_name, quantity, unit_price}]}`, y un
  listener de `inventory` consume el evento y ejecuta su propio command de alta de stock
  (p.ej. `inventory.stock.adjust` / `inventory.stock.receive`) — `purchase_orders` nunca
  escribe en tablas de `inventory`.
- Si la transición de estado y el alta de stock deben ser atómicas (recibir sin subir stock
  = inconsistente), `receive` pasaría de Tier 0 a un handler WASM que valida la guarda de
  estado (solo `confirmed`), lee las líneas y emite tanto la intención de UPDATE de estado
  como las intenciones de ajuste de stock para que el runtime las persista en una sola
  transacción. Mapear los nombres de producto a IDs de `inventory` requiere lectura previa
  (`inventory.products.list`/`get`) provista por el runtime, no por el WASM.
- Decisión abierta (matchear producto por `product_name` libre vs. exigir un `product_id` de
  inventory en la línea de PO): hoy la línea solo guarda `product_name` (texto libre), lo que
  impide un match fiable con inventory. Resolver antes de cablear la integración.
