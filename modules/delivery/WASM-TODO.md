# delivery — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_delivery/{models.py,services.py}`. El CRUD plano (zonas,
repartidores, soft-delete de pedido) ya está en SQL declarativo Tier 0 (`commands/*.sql`).
Lo que sigue es lógica de generación de número, cálculo de totales, máquina de estados,
validación cruzada y guardas de integridad que **no** cabe en una sola sentencia SQL y debe
convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas que el runtime lee
> por él, calcula y devuelve *intenciones* (filas a insertar/actualizar, sub-comandos a
> ejecutar) que el runtime valida y persiste en una transacción. Importes en decimales con
> `quantize(0.01)` (Numeric(10,2) en el modelo legacy).

---

## 1. `create_order`  (command `delivery.orders.create`)
Origen: `DeliveryService.create_order` + `DeliveryOrder.generate_number` +
`DeliveryOrder.calculate_totals` + `DeliveryOrderItem.line_total`.

- **Número atómico** `DEL-NNNN` (pieza 5).
- **Validación de zona / tarifa** (`delivery_zone_id` opcional):
  - El runtime lee la zona (`delivery_zone` por id+hub_id, no borrada). Si no existe →
    error `zone_not_found`.
  - Si `zone.is_active == 0` → error `zone_inactive` (`"Delivery zone '<name>' is not active"`).
  - Resolución de `delivery_fee`:
    - `delivery_fee` ausente/null → usar `zone.delivery_fee` (default de zona).
    - `delivery_fee` presente y zona presente → debe **coincidir** con `zone.delivery_fee`;
      si difiere → error `fee_mismatch` (mensaje legacy: "Delivery fee X does not match zone
      '<name>' configured fee of Y. Omit delivery_fee to use the zone default…").
    - Sin zona → `delivery_fee` = valor provisto o `0`.
- **driver_id**: si viene, validar formato UUID; el runtime puede comprobar existencia
  (opcional; legacy no lo valida en create).
- **Líneas** (`items[]`): por cada línea calcular `line_total = quantize(quantity * unit_price)`
  y emitir intención `_insert_item` en `delivery_order_item` (con `hub_id`, `order_id`,
  `product_name`, `quantity`, `unit_price`, `notes`).
- **Totales de cabecera** (pieza 4): `subtotal = Σ line_total`; `total = subtotal + delivery_fee`.
- Persistir cabecera `delivery_order` con `status='pending'`, `ordered_at=:now`, `paid=0`,
  campos retro-compat (`customer_name`/`customer_phone`/`delivery_address`).
- Devolver `{id, number, created: true}` y emitir `delivery.order.created`.

## 2. `update_order`  (command `delivery.orders.update`)
Origen: `DeliveryService.update_order`.

- **Máquina de estados** (solo si `status` viene en el payload). Transiciones válidas
  (igual que legacy `VALID_TRANSITIONS`):
  ```
  pending     → preparing | cancelled
  preparing   → ready | cancelled
  ready       → in_transit | picked_up | cancelled
  in_transit  → delivered | cancelled
  delivered   → (terminal)
  picked_up   → (terminal)
  cancelled   → (terminal)
  ```
  Transición no permitida → error `invalid_transition` (mensaje legacy con estado origen y
  lista de permitidos).
- **Patch parcial**: aplicar solo los campos provistos (`status`, `delivery_address`,
  `delivery_fee`, `payment_method`, `paid`, `notes`, `driver_id`, `delivery_zone_id`).
  - `driver_id`/`delivery_zone_id`: cadena vacía → `NULL`; valor → parsear UUID.
- **`completed_at`**: si la transición es a `delivered` o `picked_up` y `completed_at` está
  vacío → estampar `:now` (capacidad de reloj del host).
- **Recalcular totales** tras cambiar `delivery_fee` (totales = subtotal + delivery_fee;
  subtotal se recalcula desde las líneas vivas leídas por el runtime — pieza 4).
- Persistir cambios en `delivery_order` (`updated_by`/`updated_at`).
- Devolver `{id, number, status, updated: true}` y emitir `delivery.order.updated`.
- **Evento de negocio**: si la nueva situación es completada (`delivered`/`picked_up`),
  emitir además `delivery.order_completed` con `{order_id, number, order_type, total}`
  (el módulo se auto-escucha este evento para analítica — ver `module.json` events.listen
  y `old_modules/m_delivery/events.py`).

## 3. Cálculo de `line_total` por línea
Origen: `DeliveryOrderItem.line_total`.
- `line_total = quantize(Decimal(quantity) * unit_price, 0.01)`. Sin impuestos aparte
  (los importes del módulo delivery no desglosan IVA).

## 4. Recálculo de totales de cabecera (`subtotal`, `total`)
Origen: `DeliveryOrder.calculate_totals`.
- `subtotal = Σ line_total` sobre las líneas vivas (`is_deleted=0`).
- `total = subtotal + delivery_fee`.
- Se recalcula tanto en `create_order` (tras insertar líneas) como en `update_order`
  (tras cambiar `delivery_fee`).

## 5. Número de pedido atómico (`generate_number`)
Origen: `DeliveryOrder.generate_number`.
- Formato `DEL-NNNN` (4 dígitos), secuencia **por hub** (no por día).
- Legacy lo hace con `SELECT number ORDER BY number DESC LIMIT 1` + parseo del sufijo + 1;
  eso tiene ventana de carrera. En hub-next se resuelve como **capacidad del runtime**
  (counter UPSERT atómico por `hub_id`, sin ventana SELECT→UPDATE); el WASM solo formatea
  `DEL-{n:04d}` con el número devuelto. El índice `ix_delivery_order_hub_number`
  (UNIQUE hub_id, number) protege ante colisión.

## 6. `delete_zone`  (command `delivery.zones.delete`)
Origen: `DeliveryService.delete_zone`.
- **Guarda de dependientes**: el runtime cuenta los `delivery_order` del hub con
  `delivery_zone_id = :zone_id` y `status IN ('pending','preparing','ready','in_transit')`.
  Si `count > 0` → error `has_dependents` (mensaje legacy: "Cannot delete zone '<name>':
  N active order(s) are assigned to this zone. Complete or reassign them first.").
- Si pasa la guarda → **soft-delete** (`is_deleted=1`, `deleted_at=:now`,
  `updated_by`/`updated_at`) y emitir `delivery.zone.deleted`.
- Va a WASM porque combina un conteo condicional (read cross-tabla del propio módulo) con la
  mutación: dos pasos con guarda, no una sola sentencia.

## 7. `delete_driver`  (command `delivery.drivers.delete`)
Origen: `DeliveryService.delete_driver`.
- **Guarda de dependientes**: el runtime cuenta los `delivery_order` del hub con
  `driver_id = :driver_id` y `status IN ('pending','preparing','ready','in_transit')`.
  Si `count > 0` → error `has_dependents` (mensaje legacy: "Cannot delete driver '<name>':
  N active delivery(ies) are assigned to this driver. Complete or reassign them first.").
- Si pasa la guarda → **soft-delete** y emitir `delivery.driver.deleted`.
- Misma razón que la pieza 6 (conteo condicional + mutación).

---

## Notas de contrato cruzado (NO importar de otros módulos)
- `sale_id` en `delivery_order` es una **referencia laxa** (UUID, sin FK) al `sales.Sale`.
  delivery **no** lee ni escribe tablas de `sales`/`customers`; el vínculo se mantiene por
  evento/contrato. `depends_on: ["sales","customers"]` es solo orden de instalación.
- Los campos `customer_name`/`customer_phone`/`delivery_address` quedan como retro-compat:
  la fuente canónica del cliente es el Sale vinculado (módulo sales), vía su query pública.

## Settings (`delivery_settings`) — pendiente, no migrado a vistas
La tabla `delivery_settings` (singleton por hub: `default_prep_time`, `auto_assign_zone`)
existe en el esquema pero **no** tiene vista ni commands en esta migración (el legacy solo
exponía defaults en `SETTINGS` y un `get_settings` get-or-create). Cuando se implemente:
- query `delivery.settings.get` (get-or-create: si no existe fila para el hub, el runtime la
  crea con `default_prep_time=20`, `auto_assign_zone=1`).
- command `delivery.settings.update` (permission `delivery.change_settings`) + vista
  `erp-delivery-settings`. Mientras no exista la vista, NO añadir entrada de navegación
  (regla: sin nav muerta).
