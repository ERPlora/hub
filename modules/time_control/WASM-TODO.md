# time_control — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_time_control/{models.py,services.py}`. El CRUD plano de
centros de trabajo (workplaces) y todos los listados ya están en SQL declarativo Tier 0
(`commands/workplace_*.sql`, `queries/*.sql`). Lo que sigue es lógica de validación de
estado, cálculo geoespacial (geofencing), agregación batch y upsert con invariant legal
que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (vía queries declaradas), calcula y devuelve *intenciones* (filas a
> insertar/actualizar) que el runtime valida y persiste en una transacción. El reloj
> (`:now`) y el `:hub_id` los aporta el runtime, no el WASM.

## 1. `clock_action`  (command `time_control.records.clock`)
Origen: `TimeControlService.clock_action`.
- **Guarda de estado** (anti doble-fichaje): leer el último `ClockRecord` del empleado
  (query `time_control.records.status`).
  - Si `action_type == 'clock_in'` y el último registro es `clock_in` → error
    `already_clocked_in` ("ya fichó entrada desde <timestamp>, fiche salida primero").
  - Si `action_type == 'clock_out'` y NO está fichado (no hay último o último != `clock_in`)
    → error `not_clocked_in` ("no ha fichado entrada, fiche entrada primero").
- **Geofence** (solo si `workplace_id` no vacío): leer el workplace
  (query `time_control.workplaces.list` o equivalente por id). Si el workplace tiene
  `latitude`/`longitude` y el payload trae `latitude`/`longitude`:
  - Calcular distancia Haversine en metros (ver pieza 4).
  - `is_within_geofence = distance <= workplace.radius_meters`.
  - Si no hay coordenadas suficientes → `is_within_geofence = NULL` (no evaluado).
- Construir el `ClockRecord` a insertar: `{employee_id, employee_name, timestamp=:now,
  record_type=action_type, method, latitude, longitude, workplace_id, is_within_geofence,
  notes}` y emitir como intención de inserción.
- Devolver `{id, employee_name, action, timestamp, success:true, is_within_geofence?}`.
- Emite `time_control.clock.recorded`. **Nota**: el resumen diario NO se recalcula aquí
  automáticamente en el legacy; ver pieza 2 (comando separado / listener).

## 2. `recalculate_daily_summary`  (command `time_control.summaries.recalculate`)
Origen: `recalculate_daily_summary` (función standalone) — agregación batch.
- Leer **todos** los `ClockRecord` del empleado para `date` ordenados por `timestamp`
  ascendente (query: records_list con employee_id + date_from/date_to del día).
- Upsert del `DailySummary` único por `(hub_id, employee_id, date)`:
  - `clock_count = nº de registros`.
  - `first_clock_in` = timestamp del primer `clock_in`; `last_clock_out` = timestamp del
    último `clock_out` (o NULL si no hay).
  - **Emparejado cronológico** para minutos:
    - Variables: `total_work`, `total_break`, `pending_in=None`, `in_break=False`,
      `break_start=None`.
    - `clock_in`: si ya había un `pending_in` abierto → ese intervalo cuenta como pausa
      (`total_break += delta`); set `pending_in = ts`.
    - `clock_out` con `pending_in` abierto → `total_work += (ts - pending_in)`; cerrar
      `pending_in`.
    - `break_start` (si no en pausa) → `in_break=True`, `break_start=ts`.
    - `break_end` (si en pausa) → `total_break += (ts - break_start)`; cerrar pausa.
  - `total_work_minutes = int(total_work)`, `total_break_minutes = int(total_break)`
    (deltas en minutos: segundos/60).
  - `is_complete = bool(hubo al menos un clock_in y un clock_out)`.
- Devolver el resumen actualizado. Operación batch sobre N filas con máquina de estados
  secuencial → WASM (no expresable en una sola sentencia SQL).
- Emite `time_control.summary.recalculated`.

## 3. `update_settings`  (command `time_control.settings.update`)
Origen: `TimeControlService.update_settings`.
- **Invariant legal (RDL 8/2019)**: si `data_retention_months` viene y `< 48` → error
  `invalid_retention` ("La retención debe ser >= 48 meses, ley española RDL 8/2019").
  (El schema ya pone `minimum:48`, pero el invariant debe re-validarse en el handler:
  Rust es la única autoridad; la UI/schema es show-and-tell.)
- **Upsert del singleton** por `hub_id` (tabla `time_control_settings`, único por hub):
  - Si no existe la fila → INSERT con defaults + los campos provistos.
  - Si existe → UPDATE solo de los campos no-NULL (patrón parcial: cada bind NULL
    conserva el valor actual).
  - El upsert con rama insert/update + defaults no cabe limpio en una sola sentencia
    SQLite↔Postgres portable → handler WASM que devuelve la intención (insert o update).
- Devolver `{updated:true}`. Emite `time_control.settings.updated`.

## 4. Distancia Haversine (helper interno del handler)
Origen: `haversine` / `_haversine_meters` (services.py).
- `R = 6_371_000` m (radio terrestre).
- `dlat = radians(lat2-lat1)`, `dlon = radians(lon2-lon1)`.
- `a = sin(dlat/2)^2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)^2`.
- `distance = 2*R*asin(sqrt(a))` (equivalente: `R*2*atan2(sqrt(a), sqrt(1-a))`).
- Usado por la pieza 1 (geofence) y por `find_nearest_workplace` (legacy) si se expone
  como utilidad de cálculo en el cliente/handler.

## 5. Event listener: `staff.member_deactivated`
Origen: `events.py::_on_staff_deactivated`.
- Declarado en `module.json` (`events.listen`). El legacy solo loguea; el comportamiento
  futuro sugerido (no implementado): si el empleado desactivado tiene una sesión abierta
  (último registro `clock_in`), auto-fichar `clock_out` (`method='auto'`) reutilizando la
  lógica de la pieza 1. Cross-módulo: `time_control` NO importa de `staff` — recibe el
  evento `staff.member_deactivated` por el bus y reacciona vía sus propios comandos.

## 6. `auto_clock_out` (tarea programada, futura)
Origen: ajustes `auto_clock_out_enabled` / `auto_clock_out_hours` (no había tarea legacy
activa — `SCHEDULED_TASKS = []`). Lógica candidata a handler: para cada empleado con un
`clock_in` abierto cuya antigüedad supere `auto_clock_out_hours`, insertar un `clock_out`
`method='auto'` y recalcular el resumen (pieza 2). Documentado para cuando se cablee el
scheduler del runtime; no bloqueante.
