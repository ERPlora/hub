# kitchen — lógica pendiente para WASM Tier 2 / capacidades host

El módulo `kitchen` (Kitchen Display System) es mayoritariamente una **capa de display y
auditoría** sobre el módulo `orders` (tablas `kitchen_orders_*`). Sus dos tablas propias
(`kitchen_settings`, `kitchen_order_log`) y sus operaciones CRUD se migran como Tier 0 declarativo
(queries/commands SQL). Lo que sigue NO es CRUD declarativo y debe convertirse en handler
Rust→WASM (o resolverse como query/command cruzado del módulo `orders`) más adelante.

## 1. Display de órdenes activas (cross-module read) — `KitchenDisplayService.get_display`
- Lee `kitchen_orders_order` + `kitchen_orders_order_item` (status `pending`/`preparing`),
  agrupa por estación, filtra por `station_id`, y deriva campos calculados:
  `elapsed_minutes`, `is_delayed`, `table.number`, `item.station.name`, modifiers, seat_number.
- Es lógica de **agregación/derivación** sobre tablas de OTRO módulo → no puede ser una query SQL
  privada de `kitchen`. Debe exponerse como **query pública cruzada** del módulo `orders`
  (p.ej. `orders.kitchen.display`) o como handler WASM que orqueste varias queries del runtime.
- `warning_time_minutes`/`critical_time_minutes`/color-coding del display dependen de
  `kitchen_settings` → el cálculo de "delayed/warning/critical" (comparar elapsed vs umbrales)
  es lógica de presentación que vive en el WC o en un handler de lectura, no en SQL.

## 2. Cola de órdenes listas (cross-module read) — `KitchenDisplayService.list_ready_orders`
- Lee `kitchen_orders_order` con status `ready` ordenado por `ready_at`, con `item_count`
  derivado. Mismo caso que (1): query pública del módulo `orders`, no de `kitchen`.

## 3. Bump / recall (cross-module mutations + máquina de estados)
- `bump_item(item_id)` → `OrderItem.mark_ready()` y posible **auto-bump** del pedido si todos los
  items están listos.
- `bump_order(order_id)` → valida que TODOS los items estén `ready`/`completed` (regla de negocio
  con mensaje de error agregado), luego `Order.mark_ready()`.
- `recall_order(order_id)` → sólo si status == `ready`; `Order.recall()` devuelve a `preparing`.
- Estas operaciones **mutan tablas del módulo `orders`** y ejecutan transiciones de su máquina de
  estados (`mark_ready`/`recall`). En hub-next NO se tocan tablas de otro módulo: deben ser
  **commands públicos del módulo `orders`** (p.ej. `orders.item.bump`, `orders.order.bump`,
  `orders.order.recall`) que encapsulen la validación y la transición en su propio handler WASM.
  `kitchen` los invocaría vía SDK y, en respuesta, registraría su `kitchen.logs.create`.

## 4. Upsert parcial de settings (PATCH por-campo) — `KitchenSettingsService.update_settings`
- El legacy aplica sólo los campos no nulos y devuelve `updated_fields`. El command declarativo
  `kitchen.settings.update` persiste el estado completo (la UI envía el snapshot entero). Si se
  quisiera un PATCH real campo-a-campo con `updated_fields` (auditoría de qué cambió) habría que
  un handler WASM que haga merge con la fila existente. Marcado como mejora opcional.

## 5. Auto-accept / auto-bump (reglas temporizadas)
- `auto_accept_orders` y `auto_bump_enabled` + `auto_bump_delay_seconds` implican lógica
  **temporizada/scheduled** (aceptar/bumpear automáticamente tras N segundos). Son reglas de
  background, no CRUD: requieren un scheduled task / handler en el runtime, no SQL.

## 6. Notificaciones WebSocket en vivo (`events.py` `_push_ws` + `routes.py` `notify_kitchen_clients`)
- El legacy empuja mensajes WS a los clientes KDS (`order_new`, `order_status`) al reaccionar a
  eventos de `kitchen_orders`. En hub-next esto se cubre con el **canal de eventos del transporte**
  (WS en cloud / eventos Tauri en single): el WC se suscribe vía `erplora.on(...)`. La parte de
  auditoría de esos eventos SÍ se migra (events.listen → `kitchen.logs.create`); el push directo a
  sockets es responsabilidad del runtime/transporte, no del módulo.

## 7. Sonidos del display (sound_enabled / sound_on_new_order / sound_on_rush)
- Reproducción de audio en el cliente al recibir eventos. Es lógica de **capacidad host / UI**
  (Tier 1 host capability o pura UI en el WC), no declarativa ni WASM de datos.
