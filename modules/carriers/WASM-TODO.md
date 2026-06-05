# carriers — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_carriers/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`,
`queries/*.sql`). Lo que sigue es lógica de generación atómica de números, validación
cruzada y cálculo/filtrado que **no** cabe en una sola sentencia SQL y debe convertirse
en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, valida/calcula y devuelve *intenciones* (filas a insertar/actualizar) que el
> runtime valida y persiste en una transacción. Importes con `quantize(0.01)`; pesos
> con 3 decimales; países normalizados a ISO-2 mayúsculas.

---

## 1. `create_shipment`  (command `carriers.shipments.create`, handler WASM)
Origen: `CarriersService.create_shipment` + `_next_shipment_number`.
Es el único command que NO es SQL puro porque combina: lectura del carrier, validaciones,
generación atómica del número de envío, y el seed del tracking. Pasos:

- **Lectura previa (la hace el runtime y pasa al WASM):** el `Carrier` por `carrier_id`
  dentro del hub — campos `is_active`, `max_weight_kg`.
- **Validaciones:**
  - Carrier existe → si no, error `not_found` ("Carrier not found").
  - `carrier.is_active` == true → si no, error `carrier_inactive`.
  - `service_type` no vacío → si no, error `missing_service`.
  - `origin_address` y `destination_address` son objetos → si no, error `invalid_address`.
  - `weight_kg` y `shipping_cost` parseables a decimal → si no, error `invalid_number`.
  - Si `carrier.max_weight_kg` no es NULL y `weight_kg > max_weight_kg` →
    error `exceeds_max_weight`.
- **Generación del nº de envío (pieza 2):** `SHP-YYYYMMDD-NNNN` atómico por hub+día.
- **Seed de tracking:** `tracking_number = payload.tracking_number || "AUTO-" + shipment_number`.
- **Intención de inserción** sobre `carriers_shipment` con:
  `status='created'`, `created_at_local = now`, `reference = payload.reference || ''`,
  `origin_address`/`destination_address`/`dimensions` serializados a JSON-TEXT,
  `weight_kg`, `service_type`, `shipping_cost` y el contrato de fila estándar
  (id/hub_id/created_by/updated_by/created_at/updated_at, is_deleted=0).
- **Devolver** `{id, shipment_number, tracking_number, status}` y emitir
  `carriers.shipment.created`.

## 2. Generación atómica de `shipment_number`  (`_next_shipment_number`)
Origen: `CarriersService._next_shipment_number`.
- Formato `SHP-{YYYYMMDD}-{NNNN}` con `NNNN` = nº secuencial por hub+día (4 dígitos).
- El legacy lo hace con `COUNT(*) LIKE 'SHP-YYYYMMDD-%' + 1`, lo que tiene ventana de
  carrera (SELECT→INSERT). En hub-next debe resolverse como **capacidad de counter del
  runtime** (UPSERT atómico tipo `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`,
  igual que el contador de cotizaciones de `quotes`), invocada por el handler; el WASM
  solo formatea `SHP-{day}-{n:04d}` con el número devuelto.
- Debe ser atómico tanto en SQLite como en Postgres.

## 3. `quote_shipment`  (cotización de tarifas — query enriquecida o handler)
Origen: `CarriersService.quote_shipment`.
La query `carriers.rates.list` devuelve tarifas planas. La cotización añade lógica que no
cabe limpiamente en SQL declarativo y se documenta aquí para un handler de lectura (o una
query parametrizada ampliada si el runtime soporta comparación de decimales en binds):
- Filtrar por `origin_country`/`destination_country` (normalizados a mayúsculas).
- Filtrar por bracket de peso: `weight_from_kg <= weight_kg <= weight_to_kg`.
- Filtro opcional por `service_type`.
- **Vigencia por fecha (`is_active_on(today)`):** descartar tarifas cuyo `valid_from > hoy`
  o `valid_until < hoy` (ambos extremos opcionales/NULL = sin acotar).
- Ordenar por `price` ascendente (más barata primero).
- Devolver `{quotes:[...], total, weight_kg}`.

## 4. Filtro de vigencia en `list_rates`  (`is_active_on`)
Origen: `ShippingRate.is_active_on` aplicado en `CarriersService.list_rates` cuando se
pasa `active_on`. La query base no filtra por fecha (devuelve todas las activas no
borradas); el filtrado por `[valid_from, valid_until]` inclusive lo aplica el SDK/UI o,
si se requiere server-side, un handler que reciba las filas y la fecha de referencia.

## 5. Validaciones cruzadas de `add_rate` (no críticas para el INSERT)
Origen: `CarriersService.add_rate`.
El `commands/rate_add.sql` inserta tal cual. Estas validaciones, hoy en el servicio Python,
deben ejecutarse antes (SDK o handler de validación):
- El `carrier_id` existe dentro del hub (`not_found` si no).
- `service_type` no vacío (`missing_service`); `origin_country`/`destination_country`
  presentes (`missing_route`).
- `weight_to_kg >= weight_from_kg` (`invalid_range`).
- Normalizar `origin_country`/`destination_country`/`currency` a mayúsculas.
- Parseo de fechas `valid_from`/`valid_until` (ISO `YYYY-MM-DD` o NULL).

## 6. Guards de estado de transición (cubiertos en SQL, anotado por completitud)
Origen: `dispatch_shipment` (created→in_transit) y `mark_delivered` (in_transit→delivered).
- Implementados como UPDATE con el estado de origen EN la cláusula WHERE
  (`commands/shipment_dispatch.sql`, `commands/shipment_mark_delivered.sql`): si la
  transición no es válida, el UPDATE no afecta filas y el runtime devuelve `invalid_state`.
- No requieren WASM. Las transiciones a `returned`/`lost` del legacy no existían como
  acciones dedicadas (solo se reflejan vía estado); si se añaden, seguirán el mismo patrón.

## 7. `record_tracking_event` — default de `occurred_at`
Origen: `CarriersService.record_tracking_event`.
- El `commands/tracking_record_event.sql` recibe `:occurred_at` ya resuelto. El default
  (si el payload no trae `occurred_at` → usar `now`) y el parseo ISO (con sufijo `Z`)
  los aplica el SDK/handler antes de invocar el command. `raw_data` se serializa a JSON-TEXT.
