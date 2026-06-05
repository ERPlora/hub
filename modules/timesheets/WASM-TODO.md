# timesheets — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_timesheets/{models.py,services.py,events.py}`. El CRUD plano
(alta de tarifas, borrado lógico de registros, upsert de settings) ya está en SQL declarativo
Tier 0 (`commands/*.sql`). Lo que sigue es validación de negocio / máquina de estados /
captura de datos derivados que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas leídas por el
> runtime, valida/calcula y devuelve *intenciones* (filas a insertar/actualizar, eventos a
> emitir) que el runtime valida y persiste en una transacción. Los importes son decimales
> con `quantize(0.01)` (legacy usa `Decimal`).

---

## 1. `create_entry`  (command `timesheets.entries.create`)
Origen: `TimesheetService.create_entry`.

Lógica no-CRUD que va a WASM:
- **Validación de fecha futura**: parsear `date` (ISO `YYYY-MM-DD`); si `date > hoy` →
  error `invalid_date` ("Cannot create time entries in the future"). El "hoy" es la fecha
  UTC del reloj del host (capacidad de reloj del runtime, no del WASM).
- **Validación de duración**: `duration_minutes <= 0` → error `invalid_duration`
  ("Duration must be positive"). (El JSON Schema ya exige `exclusiveMinimum: 0`; el WASM
  lo reafirma como invariante de negocio.)
- **Captura de tarifa (`rate_amount`)**: si `hourly_rate_id` no vacío, el runtime lee la
  fila `timesheets_hourly_rate` (mismo `hub_id`) y se la pasa al WASM; el WASM copia
  `hr.rate` → `rate_amount` de la entrada. Si la tarifa no existe → `rate_amount = NULL`
  (legacy no falla: simplemente no captura). Nota: la lectura de la tarifa la hace el
  runtime, no el WASM (el WASM no toca BD).
- `status` inicial = `'draft'`.
- Devolver `{id, duration_hours, total_amount, created:true}` donde:
  - `duration_hours = round(duration_minutes / 60, 2)`.
  - `total_amount = quantize(rate_amount * duration_minutes / 60, 0.01)` si hay
    `rate_amount` y `duration_minutes`, si no `null` (ver propiedad `TimeEntry.total_amount`).

**Binds/payload**: payload = schema `entry_create.json` (`employee_id`, `employee_name`,
`date`, `duration_minutes`, `description`, `project_name`, `client_name`, `billable`,
`hourly_rate_id`). El runtime aporta `hub_id`, `current_user_id`, `now`, `today`, y la
fila de tarifa resuelta (si `hourly_rate_id` no vacío). Intención = INSERT en
`timesheets_time_entry` + emit `timesheets.entry.created`.

## 2. `update_entry`  (command `timesheets.entries.update`)
Origen: `TimesheetService.update_entry`.

Lógica no-CRUD que va a WASM:
- **Guarda de estado**: el runtime lee la entrada por `entry_id`+`hub_id`. Si no existe →
  error `not_found` ("Time entry not found"). Si `status == 'approved'` → error `approved`
  ("Cannot modify an approved time entry"). (No se puede hacer como una sola UPDATE porque
  hay que distinguir "no existe" de "está aprobada".)
- **Validación de duración**: si `duration_minutes` viene (no null) y `<= 0` →
  error `invalid_duration`.
- **Actualización parcial**: solo se aplican los campos no-null del payload
  (`duration_minutes`, `description`, `project_name`, `client_name`, `billable`) — patrón
  PATCH del legacy (`if value is not None`).
- Devolver `{id, updated:true}`.

**Binds/payload**: payload = schema `entry_update.json`. El runtime aporta `hub_id`,
`current_user_id`, `now`, y la fila actual de la entrada. Intención = UPDATE de los campos
presentes en `timesheets_time_entry` (con `updated_by`/`updated_at`) + emit
`timesheets.entry.updated`.

## 3. `approve_timesheet`  (command `timesheets.approvals.approve`)
Origen: `TimesheetService.approve_timesheet` (+ hook `timesheets.period_approved`).

Lógica no-CRUD que va a WASM (máquina de estados):
- El runtime lee el lote `timesheets_approval` por `approval_id`+`hub_id`. Si no existe →
  error `not_found` ("TimesheetApproval not found").
- **Transiciones**:
  - `status == 'approved'` → error ("Timesheet already approved").
  - `status == 'rejected'` → error ("Timesheet was rejected — cannot approve").
  - `status == 'pending'` → transición a `'approved'`.
- Al aprobar: sellar `approved_at = now` (UTC, reloj del host) y `approved_by =
  current_user_id` (cuando hay contexto de usuario; si no, queda NULL — el legacy lo
  captura "best effort").
- Devolver `{success:true, approval_id, employee_name, period_start, period_end, status,
  approved_at}`.

**Binds/payload**: payload = schema `approval_approve.json` (`approval_id`). El runtime
aporta `hub_id`, `current_user_id`, `now`, y la fila actual del lote. Intención = UPDATE de
`timesheets_approval` (status/approved_at/approved_by/updated_*) + emit
`timesheets.period_approved` (el evento que el legacy disparaba vía `hooks._registry.do_action`).

---

## Notas de eventos / cross-módulo (no WASM, contrato del runtime)
- **Listen `staff.member_deactivated`** (legacy `events.py`): cuando se desactiva un empleado,
  el legacy solo registraba un log de auditoría ("pending time entries remain but won't be
  approvable"). No muta tablas. En hub-next se declara en `module.json` (`events.listen`); si
  se quiere materializar el flag de auditoría, sería un command propio del módulo timesheets
  disparado por el listener — **nunca** un SELECT/UPDATE directo a tablas de `staff`.
- **Dependencia `staff`**: `employee_id` referencia filas del módulo `staff` (aún no migrado).
  timesheets guarda solo el `employee_id` (TEXT) + un `employee_name` denormalizado; **no**
  lee tablas privadas de `staff`. Resolver el nombre/estado del empleado se hace vía la query
  pública de `staff` desde el SDK/UI o un evento, no por JOIN.

## Notas que NO van a WASM (resueltas en Tier 0)
- `create_hourly_rate` → `commands/rate_create.sql` (validación `rate > 0` por JSON Schema).
- `delete_entry` (soft-delete con guarda `status != 'approved'`) → `commands/entry_delete.sql`
  (la guarda va en el `WHERE`; 0 filas afectadas = no existe o está aprobada).
- `update_settings` (get_or_create + setattr) → `commands/settings_update.sql` (UPSERT
  `ON CONFLICT (hub_id)`). El SDK resuelve los `None` del legacy a los valores actuales
  antes de invocar (el command escribe los 3 campos siempre).
- `list_entries` / `get_time_entry` / `list_hourly_rates` / `get_settings` /
  lista de aprobaciones → queries Tier 0 (`queries/*.sql`).

## Reportes (vista `reports` del legacy — NO migrada)
El legacy declaraba una pestaña `reports` (`view_reports`). No existía un servicio/acción
con lógica para ella en `services.py` (solo el permiso). Por la regla "sin nav muerta" **no**
se añadió entrada de navegación `reports` a `module.json`. Si se implementa, será una query
de agregación (Σ horas por empleado/periodo) o, si requiere cálculo no-SQL, un handler WASM
adicional; documentarlo aquí entonces.
