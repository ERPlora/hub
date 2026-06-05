# work_centers — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_work_centers/{models.py,services.py}`. El CRUD plano de centros
(alta + desactivación lógica) ya está en SQL declarativo Tier 0 (`commands/center_*.sql`).
Lo que sigue es lógica de fechas / cálculo de duraciones / KPIs (utilización, OEE) que **no**
cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (filas de `work_centers_event`), calcula y devuelve *intenciones* (filas a
> insertar/actualizar) o un objeto de resultado (KPIs) que el runtime valida y, si procede,
> persiste en una transacción. Las marcas de tiempo "ahora" las aporta el host (reloj).

## 1. `log_event`  (command `work_centers.events.log`)
Origen: `WorkCenterService.log_event`.
- Validar `event_type ∈ {run, stop, breakdown, setup, maintenance, idle}` (también lo cubre el JSON Schema).
- El centro `work_center_id` debe existir y no estar borrado (el runtime resuelve la lectura;
  si no existe → error `not_found`).
- Parsear `started_at` (ISO `YYYY-MM-DD` o `YYYY-MM-DDTHH:MM:SS`, acepta `Z`); si vacío/NULL →
  usar el "ahora" del host (UTC).
- Parsear `ended_at` (mismo formato) si viene.
- Derivación de cierre / duración:
  - Si `duration_minutes` viene (>= 0) y **no** hay `ended_at` → `ended_at = started_at + duration_minutes`.
  - Si `ended_at` viene y `duration_minutes` no → `duration_minutes = floor((ended_at - started_at)/60)`,
    con piso en 0 (nunca negativo).
  - Si no viene ninguno → evento **abierto**: `ended_at = NULL`, `duration_minutes = NULL`.
- Emitir la intención `_insert` sobre `work_centers_event` con todos los campos + auditoría
  (`created_by`, `created_at`, `hub_id` los inyecta el runtime).
- Devolver `{id, work_center_id, event_type, started_at, ended_at, duration_minutes, is_open}`.
- Emite evento `work_centers.event.logged`.

## 2. `end_event`  (command `work_centers.events.end`)
Origen: `WorkCenterService.end_event`.
- Leer el evento `event_id` (runtime). Guarda de estado: si `ended_at` ya no es NULL → error `already_closed`.
- Parsear `ended_at` del payload; si vacío → "ahora" del host (UTC).
- Normalizar `started_at` a tz-aware (UTC) para aritmética segura.
- Validar rango: `ended_at >= started_at`; si no → error `invalid_range`.
- `duration_minutes = floor((ended_at - started_at)/60)` (piso 0).
- Emitir intención `_update` sobre la fila: set `ended_at`, `duration_minutes`, `updated_by`, `updated_at`.
- Devolver `{id, event_type, started_at, ended_at, duration_minutes}`.
- Emite evento `work_centers.event.ended`.

## 3. Suma de minutos de eventos en ventana (`_sum_event_minutes`)
Origen: `WorkCenterService._sum_event_minutes`. Helper compartido por las piezas 4 y 5.
- Entrada: `work_center_id`, `[period_start, period_end]`, subconjunto opcional de `event_types`.
- El runtime entrega las filas de `work_centers_event` del centro con `started_at < period_end`
  (y, si se filtra, `event_type IN (...)`); el WASM agrega.
- Por cada evento **cerrado** (con `ended_at`): recortar a la ventana
  `s = max(started_at, period_start)`, `e = min(ended_at, period_end)`; si `e > s`,
  sumar `floor((e - s)/60)` minutos. Los eventos **abiertos** (sin `ended_at`) se **ignoran**
  (no se conoce su longitud real).
- Conjuntos: `PRODUCTIVE = {run}`; `PLANNED = {setup, maintenance, idle}`.

## 4. `get_utilization`  (command `work_centers.kpi.utilization`)
Origen: `WorkCenterService.get_utilization`.
- Parsear/validar `period_start`, `period_end` (ISO). Ambos requeridos; `period_end > period_start`
  → si no, error `invalid_range`.
- `total_minutes = floor((period_end - period_start)/60)`.
- `run_minutes = _sum_event_minutes(PRODUCTIVE)` (pieza 3).
- `utilization = run_minutes / total_minutes` si `total_minutes > 0`, si no `0.0` (redondear a 4 decimales).
- Solo lectura (no persiste). Devolver
  `{work_center_id, period_start, period_end, total_minutes, run_minutes, utilization}`.

## 5. `get_oee`  (command `work_centers.kpi.oee`)
Origen: `WorkCenterService.get_oee`. OEE simplificado = Availability × Performance × Quality.
- Parsear/validar período igual que en la pieza 4 (`invalid_range` si `period_end <= period_start`).
- `total_minutes`, `run_minutes = _sum_event_minutes(PRODUCTIVE)`,
  `planned_minutes = _sum_event_minutes(PLANNED)` (pieza 3).
- `operating_minutes = max(0, total_minutes - planned_minutes)`.
- **Availability** = `run_minutes / operating_minutes` si `operating_minutes > 0`, si no `0.0`.
- **Performance** (default `1.0`): solo si `total_units` viene y `run_minutes > 0` y
  `capacity_per_hour > 0` (capacidad leída del centro por el runtime):
  `run_hours = run_minutes / 60`; `expected = capacity_per_hour * run_hours`;
  si `expected > 0` → `performance = total_units / expected`.
- **Quality** (default `1.0`): solo si `good_units` y `total_units` vienen y `total_units > 0`:
  `quality = good_units / total_units`.
- `oee = availability * performance * quality` (cada factor redondeado a 4 decimales en la salida).
- Usar decimales con cuidado (los importes/ratios fiscales se calculan con precisión; aquí ratios
  a 4 decimales). Solo lectura. Devolver
  `{work_center_id, period_start, period_end, total_minutes, run_minutes, planned_minutes,
    operating_minutes, availability, performance, quality, oee}`.

## 6. Validaciones de alta de centro (Tier 1, refuerzo sobre el SQL)
Origen: `WorkCenterService.create_center`. El `INSERT` (`commands/center_create.sql`) asume payload
ya válido; estas guardas las aplica el runtime/WASM antes de ejecutarlo:
- `code` y `name` no vacíos (cubierto por el JSON Schema `center_create.json`).
- `center_type ∈ {machine, line, station, cell}` (cubierto por el enum del schema).
- `capacity_per_hour` / `hourly_cost` parseables a número >= 0.
- Guarda de **code duplicado** por hub: el índice único `ix_wc_hub_code (hub_id, code)` lo rechaza
  en BD; el handler/runtime traduce el conflicto a error de negocio `duplicate_code` en vez de
  un fallo de constraint crudo.

## 7. Guarda de desactivación (Tier 1)
Origen: `WorkCenterService.deactivate_center`. `commands/center_deactivate.sql` ya hace el
`UPDATE ... is_active=0`. La guarda "ya inactivo" (error `already_inactive` si el centro ya estaba
desactivado) la evalúa el runtime leyendo la fila antes de aplicar el UPDATE.
