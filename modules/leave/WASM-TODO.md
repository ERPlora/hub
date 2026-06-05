# leave — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_leave/{models.py,services.py,events.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
`type_create`, `type_update`, `request_update`, `request_reject`, `request_cancel`.
Lo que sigue es lógica de **cálculo / validación de saldo / upsert / batch / atomicidad**
que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (vía queries), calcula y devuelve *intenciones* (comandos `_insert_request` /
> `_set_request_status` / `_balance_insert` / `_balance_update` a ejecutar, más el evento a
> emitir) que el runtime valida y persiste en una transacción. Los días son decimales con
> `quantize(0.1)` (la columna es `NUMERIC(_,1)`: medio día = 0.5).

---

## 1. `create_request`  (command `leave.requests.create`)
Origen: `LeaveService.create_request` + `models.calculate_business_days`.

Lógica no-CRUD:
- **Parseo/validación de fechas**: `start_date`, `end_date` ISO `YYYY-MM-DD`; `start <= end`.
- **No fechas en el pasado**: `start_date >= hoy` (capacidad "reloj" del host) → error
  `start_date cannot be in the past`.
- **Antelación mínima**: leer `leave.settings.get`. Si `min_advance_days > 0`, exigir
  `start_date >= hoy + min_advance_days` → error con la fecha mínima permitida.
- **Cálculo de `days_count`**:
  - Si `is_half_day = true` → `0.5` (y conservar `half_day_period`).
  - Si no → `calculate_business_days(start, end)`: contar días **Lun–Vie** (weekday 0–4)
    inclusive entre `start` y `end`. (Sin festivos: el legacy no los modela.)
  - (Opcional / mejora) validar contra `leave_settings.max_consecutive_days`.
- **Validación de saldo**: leer `leave.balances.list` por `(employee_id, year=start.year)`,
  localizar el saldo del `leave_type_id`. Si existe y `remaining_days < days_count` →
  error `Insufficient leave balance (X remaining, Y requested)`. Si no hay saldo, se permite
  (el legacy solo bloquea cuando hay un balance explícito).

Intención de salida:
- Ejecutar `leave._insert_request` con los binds calculados (`days_count`, `is_half_day`,
  `half_day_period` o NULL, `reason`, status implícito `pending`).
- (Mejora pendiente, ver §5) sumar `days_count` a `pending_days` del saldo correspondiente.
- Emitir `leave.request.created`.
- Devolver `{id, days_count, created:true}`.

---

## 2. `approve_request`  (command `leave.requests.approve`)
Origen: `LeaveService.approve_request` + `LeaveRequest.approve`.

Lógica no-CRUD:
- Leer la solicitud (`leave.requests.get`). Si no existe → error. Guard: solo `status='pending'`
  transiciona (si no → error `Cannot approve this request (not pending)`).
- **Revalidar saldo** igual que en §1 contra `leave.balances.list` por
  `(employee_id, year=start_date.year, leave_type_id)`: si `remaining_days < days_count` →
  error de saldo insuficiente.
- Resolver `approved_by` = `current_user_id` (lo inyecta el runtime; el legacy usaba un
  placeholder porque el service no tenía contexto de usuario — en hub-next SÍ lo hay).
- `approved_at` = ahora (reloj del host).

Intención de salida:
- Ejecutar `leave._set_request_status` con `status='approved'`, `approved_by`, `approved_at`.
- **Rollup de saldo** (ver §5): mover `days_count` de `pending_days` → `used_days` en el saldo.
- Emitir `leave.request_approved` (el módulo se auto-escucha este evento — ver `events.listen`
  en `module.json`, portado de `events.py` para notificar al empleado a futuro).
- Devolver `{id, approved:true}`.

> Nota: `request_reject` y `request_cancel` SÍ son SQL Tier 0 (guard `status='pending'` en el
> WHERE). Pero si se implementa el rollup de saldo (§5), su efecto sobre `pending_days`
> (devolver los días) debería moverse también a este handler para mantener el saldo coherente.

---

## 3. `set_balance`  (command `leave.balances.set`) — UPSERT
Origen: `LeaveBalanceService.set_balance`.

Lógica no-CRUD (no es una sola sentencia: es un upsert con ramas condicionales):
- Leer `leave.balances.list` por `(employee_id, leave_type_id, year)`.
- **Si NO existe** → ejecutar `leave._balance_insert` (entitled/carried del payload;
  `used_days`/`pending_days` arrancan en 0).
- **Si existe** → ejecutar `leave._balance_update` (solo `entitled_days`/`carried_over`/
  `employee_name`; `used_days`/`pending_days` son rollups del workflow y NO se editan aquí).
- Validar que `entitled_days`/`carried_over` parseen a decimal >= 0 (el schema ya acota).
- Devolver `{id, employee_id, year, entitled_days, carried_over, saved:true}`.

> Se podría resolver con `INSERT ... ON CONFLICT(hub_id,employee_id,leave_type_id,year) DO
> UPDATE` (hay índice único), pero la semántica "no pisar used/pending" + parche parcial
> (COALESCE) lo hace más limpio como dos primitivas elegidas por el handler. Si se prefiere
> SQL puro, es viable un único `_balance_upsert.sql` — decisión de implementación.

---

## 4. `delete_leave_type`  (command `leave.types.delete`)
Origen: `LeaveTypeService.delete_leave_type`.

Lógica no-CRUD:
- **Guard referencial**: contar solicitudes que referencian el tipo
  (`SELECT COUNT(*) FROM leave_request WHERE hub_id=? AND leave_type_id=? AND is_deleted=0`,
  expuesto como query interna o capacidad del runtime). Si `count > 0` → error
  `LeaveType is referenced by N request(s). Re-classify them first.` con `requests_using_it:N`.
- Si está libre → ejecutar `commands/type_delete.sql` (soft-delete + `is_active=0`).
- Emitir `leave.type.deleted`. Devolver `{success:true, leave_type_id, name}`.

> El soft-delete en sí es Tier 0 (`type_delete.sql`); lo que va a WASM es el **conteo de
> referencias y el rechazo condicional** (leer otra tabla + decidir). Mantiene íntegros los
> balances históricos de años pasados.

---

## 5. Rollups de saldo (`pending_days` / `used_days`) — coherencia del workflow
Origen implícito: `LeaveBalance.remaining_days` + comentarios en `create_request`/`cancel_request`.

El legacy **no** mantenía los rollups automáticamente (los `pending_days`/`used_days` se
fijaban a mano vía balances). Para hub-next la transición correcta del saldo debería ser:
- `create_request` (pending) → `pending_days += days_count`.
- `approve_request` → `pending_days -= days_count`, `used_days += days_count`.
- `reject_request` / `cancel_request` (desde pending) → `pending_days -= days_count`.
- `cancel` desde `approved` (override de manager, solo UI) → `used_days -= days_count`.

Todo esto requiere leer el saldo, recalcular y escribir (`_balance_update`) dentro de la misma
transacción que la transición de la solicitud → handler WASM. **Marcado como mejora**: si no se
implementa, el saldo solo refleja lo que `set_balance` fije manualmente (paridad con el legacy).

---

## Primitivas SQL que invoca el handler (ya creadas, Tier 0)
- `leave._insert_request`  → `commands/_insert_request.sql`
- `leave._set_request_status` → `commands/_set_request_status.sql`
- `leave._balance_insert`   → `commands/_balance_insert.sql`
- `leave._balance_update`   → `commands/_balance_update.sql`

## Cross-módulo (contrato, no imports)
`depends_on: ["staff"]`. El legacy `LeaveRequest.get_employee` importaba `staff.models`. En
hub-next eso es **prohibido**: `employee_id`/`employee_name` se copian por valor al crear la
solicitud (snapshot). Si la UI necesita datos vivos del empleado, debe llamar a la query
pública del módulo staff (`staff.members.get` o similar), nunca `SELECT` directo a sus tablas.
