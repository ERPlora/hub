# tables — lógica para WASM (Tier 2)

Portado de `old_modules/m_tables/services.py`. Lo que NO es CRUD declarativo
(Tier 0) y debe convertirse en handler Rust→WASM (Extism). El WASM NO toca la BD:
recibe el payload + lecturas que el runtime le da, valida reglas, y devuelve
*intenciones* (filas a insertar/actualizar) que Rust valida y ejecuta.

Cada función mapea a un command en `module.json` con `handler.type: "wasm"`.

## bulk_create_tables  (`tables.tables.bulk_create`)
`TableService.bulk_create_tables`. Genera N mesas en un lote: itera `count` veces,
calcula `number = f"{prefix}{start_number + i}"` y reparte la posición en rejilla
(`position_x = (i % 5) * 20`, `position_y = (i // 5) * 20`). Devuelve N intenciones
de INSERT. Razón WASM: bucle + cálculo de layout, no expresable como un solo INSERT.

## open_session  (`tables.sessions.open`)
`TableService.open_session`. Reglas:
- La mesa debe existir y estar en estado `available`; si no, error `not_available`.
- Si `guests_count > table.capacity` → emite *warning* (no bloquea) con el mensaje.
- Transacción: INSERT de `tables_session` (status `active`, `opened_at = now`) +
  UPDATE de la mesa a `status = 'occupied'`.
Razón WASM: lectura-condición-escritura cruzada (mesa↔sesión) + warning de aforo.

## close_session  (`tables.sessions.close`)
`TableService.close_session` (+ `TableSession.close` del modelo). Reglas:
- La sesión debe estar `active`; si ya está `closed`/`transferred` → error con estado.
- UPDATE sesión: `status='closed'`, `closed_at=now`, append opcional de `notes`.
- UPDATE mesa asociada: `status='available'` (liberar la mesa).
Razón WASM: validación de estado + doble escritura sesión↔mesa + merge de notas.

## transfer_session  (`tables.sessions.transfer`)
`TableSession.transfer_to` (método del modelo, sin @action expuesto en legacy pero
parte del dominio). Reglas:
- Marca la sesión origen `transferred` + `closed_at=now`, libera su mesa (`available`).
- Crea una sesión nueva en la mesa destino copiando `guests_count`/`waiter_id`/`notes`,
  con `transferred_from_id = sesión origen`, y pone la mesa destino `occupied`.
Razón WASM: 4 escrituras encadenadas en una transacción atómica.

## delete_zone  (`tables.zones.delete`)
`TableService.delete_zone`. Guarda de integridad: cuenta mesas activas
(`is_active=1`, `is_deleted=0`) con `zone_id` = zona; si > 0 → rechaza con
`tables_attached`. Si no, soft-delete (`is_deleted=1`, `is_active=0`, `deleted_at=now`).
Razón WASM: count-then-mutate condicional (no es un soft-delete incondicional).

## delete_table  (`tables.tables.delete`)
`TableService.delete_table`. Guarda: cuenta sesiones `active` de la mesa; si > 0 →
rechaza con `active_sessions`. Si no, soft-delete de la mesa.
Razón WASM: count-then-mutate condicional.

## delete_session  (`tables.sessions.delete`)
`TableService.delete_session`. Guarda: rechaza si la sesión está `active`
(hay que cerrarla primero); si no, soft-delete. Conserva histórico para reporting.
Razón WASM: validación de estado previa al soft-delete.

## update_table — guardas (parcial; el UPDATE de campos es Tier 0)
`TableService.update_table`. El UPDATE plano de campos está en
`commands/table_update.sql` (Tier 0). Quedan para WASM las reglas:
- `capacity <= 0` → error `invalid_capacity`.
- Pasar `is_active=False` con la mesa NO `available` → error `active_session`.
- `status` no en (`available`,`occupied`,`reserved`,`blocked`) → error `invalid_status`.
Si se quiere enforcement server-side estricto, enrutar `tables.tables.update` a un
handler WASM que valide y delegue; mientras tanto la UI no envía valores inválidos.

## Propiedades derivadas (no persistidas — calcular en query/WASM/UI)
- `Zone.available_tables_count` y `table_count` (legacy `list_zones`): COUNT de mesas
  por zona filtrando estado/borrado. Pendiente: query agregada o cálculo en WASM.
- `TableSession.duration` / `duration_minutes`: `now - opened_at`. Se calcula en la
  UI a partir de `opened_at`/`closed_at` (no se persiste).
- Etiquetas/colores de estado (`status_label`, `status_color`, `shape_label`): mapeos
  de presentación → viven en el Web Component (ver `STATUS_LABELS`).
