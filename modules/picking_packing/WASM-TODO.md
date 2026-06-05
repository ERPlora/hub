# picking_packing — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_picking_packing/{models.py,services.py}`. Las dos transiciones
de estado triviales (start, mark_delivered) ya están en SQL declarativo Tier 0
(`commands/pick_start.sql`, `commands/package_mark_delivered.sql`), porque la guarda de estado
cabe en el `WHERE status = '...'`. Todo lo que sigue —generación de números atómicos, batch de
líneas, validaciones de cantidad/estado con mensajes específicos, recálculo de `is_complete` y
chequeo de "todas las líneas completas"— **no** cabe en una sola sentencia SQL y va a un
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime
> y devuelve *intenciones* (filas a insertar/actualizar + comandos internos como `_insert_pick`,
> `_insert_line`, `_set_pick_status`, `_set_pkg_status`, y el contador atómico) que el runtime
> valida y persiste en una transacción. Las cantidades son decimales `Numeric(12,3)` / `(10,3)`.

## 0. Contadores atómicos (capacidad de runtime invocada por el handler)
Origen: `PickCounter` / `PackageCounter` + `_next_counter` + `generate_pick_number` /
`generate_package_number` (UPSERT `INSERT ... ON CONFLICT (hub_id, day) DO UPDATE SET
last_number = last_number + 1 RETURNING last_number`).
- Tablas propias del módulo: `picking_packing_pick_counter`, `picking_packing_package_counter`.
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- `day = hoy en formato YYYYMMDD` (reloj del host).
- Formato pick: `PL-{day}-{n:04d}`. Formato paquete: `PKG-{day}-{n:04d}`.
- En hub-next el UPSERT del contador es una capacidad del runtime; el WASM solo decide qué
  contador usar y formatea la cadena con el número devuelto.

## 1. `create_pick`  (command `picking_packing.picks.create`)
Origen: `PickPackService.create_pick`.
- Validar: `lines` lista no vacía (`empty_lines`).
- Por cada línea:
  - `product_ref` no vacío tras `strip()` (`missing_product`).
  - `quantity_requested` parseable a Decimal (`invalid_quantity`) y **> 0** (`invalid_quantity`).
- Generar `pick_number` atómico (pieza 0, contador de pick).
- Emitir `_insert_pick` (cabecera): `status='draft'`, `order_ref/assigned_to_ref/notes` del payload.
- Por cada línea emitir `_insert_line`: `quantity_picked=0.000`, `is_complete=false`,
  `location_ref`/`lot_ref` del payload (default '').
- Todo en una transacción. Devolver `{id, pick_number, order_ref, status, lines_count}`.
- Emite evento `picking_packing.pick.created`.

## 2. `record_pick_line`  (command `picking_packing.picks.record_line`)
Origen: `PickPackService.record_pick_line` + `PickLine.refresh_completion`.
- Leer la pick list (`pick_list_not_found` si no existe).
- Guarda de estado: la pick debe estar en `draft` o `in_progress` (`invalid_state` si no).
- Leer la línea por `line_id` y comprobar que `pick_list_id` coincide (`line_not_found`).
- `quantity_picked` parseable (`invalid_quantity`) y **>= 0** (negativo → `invalid_quantity`).
- Actualizar `quantity_picked`; si llega `location_ref` no vacío, actualizarlo.
- Recalcular `is_complete` = `quantity_picked >= quantity_requested AND quantity_requested > 0`
  (cubre el over-pick: sigue contando como completa).
- Persistir vía `_set_line`. Devolver `{id, pick_list_id, quantity_picked, is_complete}`.
- Emite evento `picking_packing.pick.line_recorded`.

## 3. `complete_pick`  (command `picking_packing.picks.complete`)
Origen: `PickPackService.complete_pick`.
- Leer la pick (`pick_list_not_found`).
- Guarda: solo desde `in_progress` (`invalid_state`).
- Leer todas las líneas; si no hay → `empty_pick`.
- Contar líneas con `is_complete = false`; si hay alguna → error `lines_incomplete`
  con `incomplete_count = N` en el detalle.
- Si todas completas: `_set_pick_status` a `completed` + `completed_at = now`.
- Devolver `{id, pick_number, status, completed_at}`. Emite `picking_packing.pick.completed`.

## 4. `cancel_pick`  (command `picking_packing.picks.cancel`)
Origen: `PickPackService.cancel_pick`.
- Leer la pick (`pick_list_not_found`).
- Guardas: `completed` → error `completed_locked`; `cancelled` → error `already_cancelled`.
- Transicionar a `cancelled`. Si llega `reason` no vacío, **anexar** a `notes` el rastro
  `"\n[CANCELLED] {reason}"` (compone el nuevo texto de notes → necesita el valor actual de
  notes leído por el runtime; no es una UPDATE plana porque concatena texto existente).
- Devolver `{id, pick_number, status}`. Emite `picking_packing.pick.cancelled`.

## 5. `create_package`  (command `picking_packing.packages.create`)
Origen: `PickPackService.create_package`.
- `weight_kg` parseable (`invalid_weight`) y **>= 0** (negativo → `invalid_weight`).
- Generar `package_number` atómico (pieza 0, contador de paquete).
- Emitir `_insert_package`: `status='open'`, `pick_list_ref`/`carrier` del payload (default ''),
  `dimensions=''`, `tracking_number=''`, `packed_by_ref=''`.
- Devolver `{id, package_number, status, weight_kg}`. Emite `picking_packing.package.created`.

## 6. `seal_package`  (command `picking_packing.packages.seal`)
Origen: `PickPackService.seal_package`.
- Leer paquete (`package_not_found`).
- Guarda: solo desde `open` (`invalid_state`).
- Transicionar a `sealed` + `packed_at = now`. Si llega `tracking_number` no vacío, fijarlo.
- (Opcional, no en el legacy: fijar `packed_by_ref = current_user_id`.)
- Devolver `{id, package_number, status, tracking_number, packed_at}`. Emite
  `picking_packing.package.sealed`.

## 7. `ship_package`  (command `picking_packing.packages.ship`)
Origen: `PickPackService.ship_package`.
- `tracking_number` requerido y no vacío (`missing_tracking`) — ya forzado por el schema, pero
  el handler revalida (el SDK `hasPermission`/schema es de cortesía; Rust es la autoridad).
- Leer paquete (`package_not_found`).
- Guarda: solo desde `sealed` (`invalid_state`).
- Transicionar a `shipped` + fijar `tracking_number`.
- Devolver `{id, package_number, status, tracking_number}`. Emite `picking_packing.package.shipped`.

## Notas sobre la máquina de estados (referencia)
- Pick: `draft → in_progress → completed`; `cancelled` desde cualquier estado salvo `completed`.
- Paquete: `open → sealed → shipped → delivered`; `returned` existe en el dominio pero el
  legacy no expone transición hacia él (no se migra command; se deja el valor en el enum del esquema).
- `pick_start` y `package_mark_delivered` se quedan en Tier 0 SQL (guarda en WHERE). El resto
  necesita lectura previa + validación condicional con mensajes de error específicos → WASM.

## Eventos emitidos (contrato cross-módulo)
`picking_packing.pick.created` / `.started` / `.line_recorded` / `.completed` / `.cancelled`,
`picking_packing.package.created` / `.sealed` / `.shipped` / `.delivered`.
Otros módulos (p.ej. inventory para descontar stock al `shipped`, o sales para marcar el pedido
servido) se enganchan por **evento**, nunca importando ni tocando las tablas de este módulo.
