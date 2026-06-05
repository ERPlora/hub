# courier_integrations — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_courier_integrations/{models.py,services.py}`. El CRUD plano
de conexiones (alta + desactivación lógica) y los listados ya están en SQL declarativo
Tier 0 (`commands/connection_*.sql`, `queries/*.sql`). Lo que sigue es lógica de
secuenciación atómica, simulación de carrier API, escritura multi-tabla atómica y
agregación que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. El secuenciador de `call_number` y el reloj (`now`)
> son **capacidades del host**: el WASM las invoca, no las implementa.

## 0. Secuenciador de número de llamada (`_next_call_number`)
Origen: `services._next_call_number`.
- Formato `CAPI-YYYYMMDD-NNNN`: `NNNN` = secuencia por hub + día, 4 dígitos.
- En legacy era `COUNT(call_number LIKE 'CAPI-<day>-%') + 1` (ventana de carrera).
- En hub-next se resuelve como **counter UPSERT atómico** del runtime (igual que el contador
  de cotizaciones de `quotes`): el WASM solo formatea `CAPI-{day}-{n:04d}` con el nº devuelto.
- Lo usan TODOS los commands WASM de abajo (cada uno graba un `APICall`).

## 1. `record_call`  (command `courier_integrations.calls.record`)
Origen: `CourierService.record_call`.
- Validar `call_type ∈ {create_shipment, get_label, track_shipment, cancel_shipment, get_rate}`
  (ya cubierto por JSON Schema; revalidar en host).
- Resolver la conexión por `connection_id` (lectura runtime, mismo hub) → error si no existe.
- Generar `call_number` (pieza 0) y `now` (reloj host).
- Intenciones, atómicas en una transacción:
  - INSERT en `courier_integrations_api_call` (request/response payload como JSON-string,
    `status_code`, `status`, `response_time_ms`, `error_message`).
  - UPDATE de la conexión: `last_call_at = now`, `last_call_status = status`.
- Emite `courier_integrations.call.recorded`.

## 2. `create_shipment_via_courier`  (command `courier_integrations.shipments.create`)
Origen: `CourierService.create_shipment_via_courier` + `_simulate_create_shipment`.
- Resolver conexión; error `connection_inactive` si `is_active = 0`.
- Guarda de duplicado: rechazar si ya existe un `ShipmentMapping` con el mismo
  `(connection_id, local_shipment_ref)` → error `duplicate_local_ref` (lectura runtime).
- **Simulación de carrier (placeholder, reemplazable por `http.fetch` Tier 1):**
  - `seed = "{courier_code}:{ref}:{uuid4_hex[:8]}"`; `digest = SHA1(seed).hex().upper()`.
  - `tracking = "{COURIER_CODE}-{digest[:14]}"`.
  - `label_url = "https://labels.example/{courier_code}/{digest[:14]}.pdf"`.
  - `response_payload = {tracking_number, label_url, courier, status:"created"}`.
- Intenciones, atómicas:
  - INSERT `ShipmentMapping` (`external_tracking_number=tracking`, `label_url`,
    `status_at_courier="created"`, `last_synced_at=now`).
  - INSERT `APICall` (`call_type="create_shipment"`, `status_code=201`, `status="success"`).
  - UPDATE conexión `last_call_at/last_call_status`.
- Devolver `{shipment_mapping_id, external_tracking_number, label_url, call_number}`.
- Emite `courier_integrations.shipment.created`.

## 3. `get_label_url`  (command `courier_integrations.shipments.get_label`)
Origen: `CourierService.get_label_url`.
- Resolver mapping por `shipment_mapping_id`; error `label_missing` si `label_url` vacío.
- Resolver la conexión asociada.
- Intenciones, atómicas:
  - INSERT `APICall` (`call_type="get_label"`, `status_code=200`, request con
    `{shipment_mapping_id, tracking_number}`, response `{label_url}`).
  - UPDATE conexión `last_call_at/last_call_status="success"`.
- Devolver `{shipment_mapping_id, label_url, call_number}`.
- (No emite evento en legacy; el manifest tampoco declara `emit`.)

## 4. `track_shipment_via_courier`  (command `courier_integrations.shipments.track`)
Origen: `CourierService.track_shipment_via_courier` + `_simulate_track`.
- Resolver mapping; error `missing_tracking` si no hay `external_tracking_number`.
- Simulación: `response = {tracking_number, status:"in_transit", checkpoints:[{at:now, label:"Picked up"}]}`.
  `new_status = response.status` (fallback al `status_at_courier` actual).
- Intenciones, atómicas:
  - UPDATE mapping `status_at_courier=new_status`, `last_synced_at=now`.
  - INSERT `APICall` (`call_type="track_shipment"`, `status_code=200`).
  - UPDATE conexión `last_call_*`.
- Devolver `{shipment_mapping_id, status_at_courier, tracking_number, call_number}`.
- Emite `courier_integrations.shipment.tracked`.

## 5. `cancel_shipment_via_courier`  (command `courier_integrations.shipments.cancel`)
Origen: `CourierService.cancel_shipment_via_courier` + `_simulate_cancel`.
- `reason` requerido (JSON Schema lo cubre).
- Resolver mapping; error `already_cancelled` si `status_at_courier == "cancelled"`.
- Simulación: `response = {tracking_number, status:"cancelled", reason}`.
- Intenciones, atómicas:
  - UPDATE mapping `status_at_courier="cancelled"`, `last_synced_at=now`.
  - INSERT `APICall` (`call_type="cancel_shipment"`, `status_code=200`, request con `{tracking_number, reason}`).
  - UPDATE conexión `last_call_*`.
- Devolver `{shipment_mapping_id, status_at_courier, call_number}`.
- Emite `courier_integrations.shipment.cancelled`.

## 6. `get_api_metrics`  (command `courier_integrations.metrics.get`, solo lectura/agregación)
Origen: `CourierService.get_api_metrics`.
- `period_days > 0` (JSON Schema: minimum 1).
- Ventana: `since = now - period_days días`. Leer (runtime) los `APICall` de la conexión
  con `called_at >= since`.
- Agregar en WASM:
  - `total_calls`, `success_calls` (status=success), `failed_calls` (failed),
    `timeout_calls` (timeout).
  - `success_rate = round(success/total, 4)` (0.0 si total=0).
  - `avg_response_time = round(mean(response_time_ms), 2)` (0.0 si total=0).
- Devolver `{connection_id, period_days, total_calls, success_calls, failed_calls,
  timeout_calls, success_rate, avg_response_time}`.
- Es solo agregación (no muta) pero requiere leer N filas + cálculo → no cabe en una query
  declarativa simple sin múltiples agregaciones; se modela como handler WASM de solo lectura.

## Notas de migración / cross-módulo
- El módulo es **independiente** (legacy `DEPENDENCIES = []`): "extiende" conceptualmente al
  módulo `carriers` pero NO importa su esquema. `local_shipment_ref` es una referencia opaca;
  cualquier vínculo con envíos de otro módulo debe hacerse vía contrato de eventos/queries
  públicos, nunca tocando tablas privadas ajenas.
- Las credenciales reales de la API (hoy `api_credentials_hash`) NO se exponen al WC ni se
  devuelven en queries; cuando se sustituyan los `_simulate_*` por `http.fetch` (Tier 1), la
  resolución de credenciales será una capacidad mediada del host, no lógica WASM.
- `get_rate` aparece en el enum `CALL_TYPES` pero no tenía servicio dedicado en legacy; se
  conserva como tipo de llamada válido para `record_call` (futuro tarifador).
