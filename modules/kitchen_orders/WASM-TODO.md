# kitchen_orders — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_commands/{models.py,services.py,events.py}` (MODULE_ID =
`kitchen_orders`; el paquete Python se quedó como `commands/` por el rename del repo).
El CRUD plano (estaciones, settings, update/delete de comanda, enrutado) ya está en SQL
declarativo Tier 0 (`commands/*.sql`). Lo que sigue es lógica de batch / cálculo /
transición / resolución cross-módulo que **no** cabe en una sola sentencia SQL y debe
convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (vía queries del propio módulo o de otros módulos por contrato), calcula y
> devuelve *intenciones* (comandos `kitchen_orders._insert_order` / `_insert_item` /
> `_set_order_status` / `_set_item_status` / `_order_soft_delete` / `_station_soft_delete`)
> que el runtime valida y persiste en una transacción. Los importes son decimales con
> `quantize(0.01)`.
>
> **Cross-módulo = contrato, nunca import.** Para resolver producto (nombre/precio) o
> categoría, el handler pide al runtime que ejecute la query pública de inventory
> (`inventory.products.get`), nunca un SELECT directo a las tablas de inventory.

---

## 1. `create_order`  (command `kitchen_orders.orders.create`)
Origen: `OrderService.create_order` + `Order.calculate_totals` + `OrderItem.recalculate_total`.
- Validar: `order_type ∈ {dine_in, takeaway, delivery}`; normalizar `table_id`/`customer_id`/
  `waiter_id` vacíos → NULL.
- Generar `order_number` atómico → ver pieza 6 (counter `YYYYMMDD-NNNN`).
- Por cada item del payload:
  - Resolver el snapshot de producto vía la query pública **`inventory.products.get`**
    (`product_id`) → `product_name`, `unit_price`. Si no existe → error
    `product_not_found` (con el id). Si inventory no está instalado → error
    `inventory_unavailable`. (NO leer tablas de inventory directamente.)
  - Resolver la estación destino → ver pieza 5 (routing). `station_id` puede quedar NULL.
  - `line_total = quantize(unit_price * quantity, 0.01)`.
  - Emitir `kitchen_orders._insert_item` con el snapshot, `line_total`, `status='pending'`.
- Calcular totales de cabecera (pieza 4) y emitir `kitchen_orders._insert_order` con
  `status='pending'`, `priority`, `notes`, subtotal/tax/discount/total.
- Devolver `{id, order_number, items:[{product, quantity}], total, created:true}`.
- El runtime emite `kitchen_orders.order.created` tras commit.

## 2. `update_order_status`  (command `kitchen_orders.orders.set_status`)
Origen: `OrderService.update_order_status`. Transición de la comanda **con cascada a sus
líneas** y marcas de tiempo del reloj del host (`:now`). Por eso no es un único UPDATE:
hay que leer las líneas activas y aplicar cambios condicionados por su estado.
- Leer la comanda (`kitchen_orders.orders.get`) y sus líneas (`kitchen_orders.orders.items`).
  Si no existe → error `order_not_found`.
- Según `action_name`:
  - `fire`: comanda → `preparing`, `fired_at = now`. Cada línea `pending` → `preparing`,
    `fired_at = now`. Emite evento `kitchen_orders.order.fired`.
  - `mark_ready`: comanda → `ready`, `ready_at = now`. Emite `...order.ready`.
  - `mark_served`: comanda → `served`, `served_at = now`. Emite `...order.served`.
  - `cancel`: comanda → `cancelled`; si `reason` no vacío, `notes = (notes + "\nCancelled: " + reason).strip()`.
    Todas las líneas no borradas → `cancelled`. Emite `...order.cancelled`.
  - `recall`: SOLO si la comanda está en `ready` → `preparing`, `ready_at = NULL`; cada
    línea `ready` → `preparing`, `completed_at = NULL`. (Sin evento.)
  - cualquier otro → error `unknown_action`.
- Emitir un `kitchen_orders._set_order_status` para la cabecera y un
  `kitchen_orders._set_item_status` por cada línea afectada.
- Devolver `{id, order_number, status, updated:true}`.
- **Permisos finos**: el manifest usa `change_order` para todo `set_status`. Si se quiere
  honrar los permisos legacy `cancel_order` / `complete_order` por acción, el handler debe
  pedir al runtime una comprobación de permiso adicional según `action_name`
  (cancel→`cancel_order`, mark_served→`complete_order`) antes de aplicar.

## 3. `delete_order`  (command `kitchen_orders.orders.delete`)
Origen: `OrderService.delete_order`. Guarda de estado que necesita leer la fila primero.
- Leer la comanda. Si no existe → error `order_not_found`.
- Si `status NOT IN ('pending','cancelled')` → error `cannot_delete_status`.
- Si `sale_id IS NOT NULL` → error `linked_to_sale` ("anula/reembolsa la venta primero").
- Si pasa, emitir `kitchen_orders._order_soft_delete`. Devolver `{deleted:true, order_number}`.
- El runtime emite `kitchen_orders.order.deleted`.

## 4. Recálculo de totales de la comanda (`subtotal`, `total`)
Origen: `Order.calculate_totals`.
- `subtotal = Σ line_total` de las líneas no borradas.
- `total = subtotal - discount + tax` (discount/tax por defecto 0). `quantize(0.01)`.
- `tax` y `discount` no se calculan aquí en el flujo legacy (llegan 0 al crear); si en el
  futuro la comanda toma impuestos del módulo `taxes`, hacerlo vía su query pública.

## 5. Resolución de estación por producto (routing)
Origen: `get_station_for_product` (models.py). Prioridad: mapeo directo de producto >
mapeo por categoría > NULL.
- Buscar en `kitchen_orders_product_station` por `product_id` (query interna del módulo).
  Si hay y la estación está activa → usarla.
- Si no, resolver la **categoría del producto** vía la query pública
  `inventory.products.get` (campo `category_id`), buscar en `kitchen_orders_category_station`
  por esa categoría; si hay y la estación está activa → usarla.
- Si nada coincide → `station_id = NULL`.
- (Necesita una query interna `routing.resolve` o que el runtime exponga lectura de las dos
  tablas de routing al handler; ambas son tablas PROPIAS de kitchen_orders, OK.)

## 6. Contador atómico de nº de comanda (`generate_order_number`)
Origen: `generate_order_number` (models.py). Formato `YYYYMMDD-NNNN` (NNNN = secuencia por
hub+día, 4 dígitos). El legacy hace SELECT del último + parseo, lo cual NO es atómico.
- En hub-next se resuelve como **capacidad del runtime** (counter UPSERT
  `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`, portable SQLite/Postgres) invocada por
  el handler; el WASM solo formatea `{day}-{n:04d}` con el número devuelto.
- Sin ventana SELECT→UPDATE (evita colisiones de order_number en alta concurrente).

## 7. `delete_station`  (command `kitchen_orders.stations.delete`)
Origen: `KitchenStationService.delete_station`. Guardas que requieren conteos previos.
- Contar enrutados de la estación: `product_station` + `category_station` por `station_id`.
  Si total > 0 → error `station_has_routings` (reasignar/quitar primero).
- Contar líneas en curso (`order_item.status IN ('pending','preparing')`) con esa
  `station_id`. Si > 0 → error `station_has_active_items`.
- Si pasa, emitir `kitchen_orders._station_soft_delete`. Devolver `{deleted:true, name}`.
- (Legacy hacía `hard_delete`; en hub-next es soft-delete por el contrato §2.5.)
- El runtime emite `kitchen_orders.station.deleted`.

## 8. `set_routing`  (command `kitchen_orders.stations.set_routing`)
Origen: `KitchenStationService.set_routing`. Upsert de uno o ambos mapeos.
- Validar que `station_id` exista y esté activa (lectura de tabla propia).
- Si `product_id` no vacío → emitir `kitchen_orders._product_route_set` (UPSERT por hub+product).
- Si `category_id` no vacío → emitir `kitchen_orders._category_route_set` (UPSERT por hub+category).
- Al menos uno de los dos debe venir (si no → error `nothing_to_route`).
- Devolver `{product_routing?, category_routing?}` indicando created/updated.
- El runtime emite `kitchen_orders.routing.changed`.
- Nota: los dos UPSERT son Tier 0 (`commands/product_route_set.sql`,
  `category_route_set.sql`); el WASM solo orquesta cuál(es) ejecutar + la validación.

## 9. `create_order_from_sale`  (command `kitchen_orders.orders.create_from_sale`, EVENT-driven)
Origen: `events.py::_on_kitchen_order_required` (legacy escuchaba `kitchen.order_required`;
en hub-next se reengancha al evento estándar **`sale.completed`** — ver `module.json`
`events.listen`, mismo patrón que inventory `stock.decrease_on_sale`).
- Payload del evento (del módulo sales, por contrato): `{hub_id, sale_id, table_id?,
  channel, items:[{product_id?, product_name?, quantity, notes?}]}`.
- **Idempotencia**: buscar una comanda existente con ese `sale_id` (query interna). Si
  existe → no-op (skip), devolver `{skipped:true, order_number}`.
- Derivar `order_type`: `dine_in` si hay `table_id`; si no, `takeaway` cuando `channel='pos'`,
  o el propio `channel` en otro caso.
- Generar `order_number` (pieza 6), emitir `_insert_order` (`status='pending'`,
  `priority='normal'`, `sale_id`, `table_id`) + un `_insert_item` por línea
  (`status='pending'`; resolver estación con pieza 5).
- El runtime emite `kitchen_orders.order.created` tras commit.
- Cross-módulo: kitchen_orders **no** importa de sales; consume el evento (contrato), no el
  código. La idempotencia es obligatoria porque el bus puede reentregar el evento.
