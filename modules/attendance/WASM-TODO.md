# attendance — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_attendance/{models.py,services.py}`. El CRUD plano de la
configuración (`settings_update`) y las primitivas de fila (`_insert_record`,
`_close_record`, `_update_record`, `_delete_record`, `_insert_settings`) ya están en SQL
declarativo Tier 0. Lo que sigue es lógica de cálculo / validación / guardas de estado
que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (vía las queries públicas `attendance.records.open` / `attendance.records.list`),
> calcula y devuelve *intenciones* (comandos `_insert_record` / `_close_record` /
> `_update_record` / `_delete_record` a ejecutar) que el runtime valida y persiste en una
> transacción. `total_hours` se calcula con `quantize(0.01)` (NUMERIC(5,2) en el legacy).

## 1. `clock_in`  (command `attendance.records.clock_in`)
Origen: `AttendanceService.clock_in`.
- Validar: `employee_id` no vacío y parseable como UUID; `employee_name` no vacío.
- **Guarda de unicidad**: leer el fichaje abierto del empleado vía `attendance.records.open`
  (`employee_id`, `clock_out IS NULL`). Si existe → error `already_clocked_in` con mensaje
  "<nombre> ya está fichado desde <clock_in>. Fiche la salida primero."
- `status` por defecto `present`; debe estar en `{present, late, absent, half_day, remote}`.
- Sellar `clock_in = now` (capacidad de reloj del host) y emitir `_insert_record` con
  `clock_out=NULL`, `break_minutes=0`, `total_hours=0`, `notes`, `location`/`device` (opcional).
- Devolver `{id, employee_name, clock_in, clocked_in:true}` y emitir `attendance.record.clocked_in`.

### 1.b Política de horario (F6.C — `SCHEDULE_ENFORCEMENT_POLICY`)
Origen: constante `SCHEDULE_ENFORCEMENT_POLICY` del manifest legacy (`"off" | "warning" | "strict"`).
- Si el empleado ficha **fuera del horario** de negocio:
  - `off` → silencioso.
  - `warning` → registrar aviso (no bloquea); valor por defecto.
  - `strict` → rechazar con error `outside_schedule` (equivalente a 409).
- El horario procede del módulo `schedules`/`staff` (dependencia `staff`); el runtime lo
  resuelve vía contrato público (query cross-módulo), **nunca** leyendo tablas ajenas.
  Si el horario no está disponible, tratar como `off`. NOTA: en el legacy esta política
  quedó declarada pero la comprobación contra el horario no estaba implementada — migrarla
  aquí es opcional/no bloqueante.

## 2. `clock_out`  (command `attendance.records.clock_out`)
Origen: `AttendanceService.clock_out` + `AttendanceRecord.calculate_total_hours`.
- Leer el fichaje abierto del empleado vía `attendance.records.open`. Si no hay → error
  `not_clocked_in` ("El empleado no está fichado. No hay registro abierto.").
- Sellar `clock_out = now`.
- `break_minutes`: si viene > 0, usarlo; si no, conservar el actual.
- **Cálculo de `total_hours`** (`calculate_total_hours`):
  - `delta_min = (clock_out - clock_in) en minutos`.
  - `worked_min = max(delta_min - break_minutes, 0)`.
  - `total_hours = quantize(worked_min / 60, 0.01)`.
- Si viene `notes`, sobreescribir; si no, conservar.
- Emitir `_close_record` con `{record_id, clock_out, break_minutes, total_hours, notes}` y
  emitir `attendance.record.clocked_out`.
- Devolver `{id, employee_name, clock_in, clock_out, total_hours, clocked_out:true}`.

## 3. `update_record`  (command `attendance.records.update`, corrección de manager)
Origen: `AttendanceService.update_record`.
- Validar `record_id` parseable como UUID → si no, error `invalid_record_id`.
- Cargar el registro (vía query/lectura del runtime). Si no existe → error `not_found`.
- Aplicar parciales (sólo los campos enviados):
  - `clock_in` / `clock_out`: parsear ISO-8601. `clock_out == ""` → NULL (reabre el fichaje).
    ISO inválido → error `invalid_clock_in` / `invalid_clock_out`.
  - **Guarda temporal**: si tras el edit `clock_out` no es NULL y `clock_out < clock_in` →
    error `clock_out_before_clock_in`.
  - `break_minutes` → `max(0, int)`.
  - `status`, `notes`, `location` → asignación directa.
- **Recalcular `total_hours`** sólo si `clock_out` no es NULL:
  - `delta_h = (clock_out - clock_in) en horas`.
  - `hours = quantize(delta_h, 0.01) - (break_minutes / 60)`.
  - `total_hours = max(0.00, hours)`.
  (Nota: difiere ligeramente del orden de operaciones de `clock_out`; portar tal cual el
  legacy — primero quantize del delta en horas, luego resta del descanso.)
- Emitir `_update_record` con el conjunto resultante y emitir `attendance.record.updated`.
- Devolver `{id, total_hours, status, updated:true}`.

## 4. `delete_record`  (command `attendance.records.delete`, soft-delete)
Origen: `AttendanceService.delete_record`.
- Validar `record_id` UUID → si no, error `invalid_record_id`.
- Cargar el registro. Si no existe → error `not_found`.
- **Guarda de integridad**: si `clock_out IS NULL` (fichaje ABIERTO) → error
  `cannot_delete_open` ("No se puede borrar un fichaje ABIERTO. Cierre el clock_out
  primero vía update_record."). Mantiene consistente el rollup de horas.
- Emitir `_delete_record` (soft-delete: `is_deleted=1`, `deleted_at=now`) y emitir
  `attendance.record.deleted`.
- Devolver `{success:true, record_id}`.

## 5. Estadísticas (`get_stats`) — Tier 1 (no migrado a command, opcional)
Origen: `AttendanceService.get_stats`. Agrega un rango de fechas en conteos por estado
(`present/late/absent/half_day/remote`) + `total_hours` sumado. Es de sólo lectura y
batch; puede resolverse:
- como query SQL con `GROUP BY status` + `SUM(total_hours)` (agregado simple), o
- en el handler si se quiere el mismo shape exacto del legacy (`{period, total_records,
  total_hours, present, late, ...}`).
No se ha incluido en `module.json` todavía (sin vista de dashboard migrada — sólo se
migraron las vistas `records` y `settings`). Añadir cuando se implemente la vista dashboard.

## 6. Listener `staff.member_deactivated` (cross-módulo)
Origen: `events.py::_on_staff_deactivated`. En el legacy sólo registra un log de trazabilidad
(no auto-cierra fichajes). Declarado en `module.json` (`events.listen`). El comportamiento
futuro sugerido (auto-clock-out de sesiones abiertas del empleado desactivado) sería un
handler WASM que: lee los fichajes abiertos del `employee_id` (query `attendance.records.open`)
y emite `_close_record` para cada uno. Hoy no bloqueante — el listener puede ser no-op/log.
