# staff — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_staff/{models.py,services.py,routes.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`).
Lo que sigue es lógica de validación cruzada / batch / multi-tabla atómica que **no** cabe
en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, valida/calcula y devuelve *intenciones* (filas a insertar/actualizar) que el
> runtime persiste en una transacción. El reloj (fecha de hoy) es capacidad del host.

## 1. `deactivate_staff_member`  (command `staff.members.deactivate`)
Origen: `StaffService.deactivate_staff_member`.
- Lee el miembro por `staff_id` (runtime lo provee). Si no existe → error `not_found`.
- **Guarda de estado**: si `status == 'inactive'` → error `already_inactive`;
  si `status == 'terminated'` → error `already_terminated`.
- **Invariant cruzado**: contar `staff_time_off` del miembro con `status IN ('pending','approved')`
  y `end_date >= hoy`. Si hay > 0 → error
  `"Cannot deactivate: N active time-off request(s) exist. Cancel or resolve them first."`.
  (No es un `deactivate` puro: requiere leer otra tabla del propio módulo y razonar con la
  fecha de hoy, por eso no es Tier 0.)
- Intención: `UPDATE staff_member SET status='inactive', is_bookable=0` (NO soft-delete:
  desactivar ≠ terminar). Emite `staff.member.deactivated`.

## 2. `bulk_create_staff_members`  (command `staff.members.bulk_create`)
Origen: `StaffService.bulk_create_staff_members`.
- Itera sobre `members[]`; por cada item valida `first_name`/`last_name` y parsea `hire_date`
  (ISO `YYYY-MM-DD` o vacío → NULL) y `hourly_rate` (decimal, default 0).
- Tolerante a fallos por fila: acumula `errors[]` con `{name, error}` y sigue con el resto
  (no aborta todo el lote). Devuelve `{success:true, created:N, errors:[...]}`.
- Intención: N filas `INSERT` en `staff_member` (las válidas). Operación batch con resultado
  agregado → no cabe en una sentencia; va a WASM.

## 3. `create_schedule`  (command `staff.schedules.create`)
Origen: `routes.schedule_create` (`POST /staff/{member_id}/schedules/create`).
- Inserta una fila en `staff_schedule` + N filas en `staff_working_hours` (una por día con
  `day_of_week` 0..6). **Multi-tabla atómica**: todo o nada.
- **Regla de unicidad de horario por defecto**: si el nuevo `is_default == 1`, desmarcar
  (`is_default=0`) los demás horarios del mismo `staff_id` antes de insertar (solo un default
  por miembro).
- Validar working_hours: `start_time < end_time`; si hay `break_start`/`break_end`, que el
  break caiga dentro del intervalo; `(schedule_id, day_of_week)` único (lo refuerza el índice).
- Intención: 1 `INSERT` schedule + UPDATE de desmarcado + N `INSERT` working_hours. Emite
  `staff.schedule.created`.

## 4. `create_time_off`  (command `staff.time_off.create`)
Origen: `StaffMemberCreate` + `StaffTimeOff.conflicts_with` (modelo legacy) +
`routes` de time-off.
- Validar: `start_date <= end_date`; `leave_type` en el enum; si `is_full_day == 0` exigir
  `start_time`/`end_time` coherentes.
- **Invariant de solapamiento** (`StaffTimeOff.conflicts_with`): rechazar si el miembro ya
  tiene otra ausencia con `status IN ('pending','approved')` cuyo rango `[start_date,end_date]`
  se solapa con el nuevo. Regla legacy: solapan si NO (`new_end < existing_start OR
  new_start > existing_end`). Si solapa → error `overlapping_time_off`.
  (Requiere leer las ausencias existentes del miembro y comparar rangos → no es un INSERT puro.)
- Intención: 1 `INSERT` en `staff_time_off` con `status='pending'`. Emite `staff.time_off.created`.

## 5. Notas no-bloqueantes (Tier 0/Tier 1, ya cubiertas o triviales)
- `staff.time_off.set_status` (approve/reject/cancel) ya es Tier 0 (`commands/time_off_set_status.sql`).
  Si se quiere endurecer las transiciones permitidas (p.ej. no aprobar una `cancelled`) y
  re-chequear solapamiento **al aprobar**, esa validación subiría a un handler WASM análogo
  al §4; hoy se deja como transición simple.
- `staff.members.delete` (terminación) ya es Tier 0 (`commands/member_delete.sql`): soft-delete +
  `status='terminated'` + `termination_date=hoy` (`:today` lo inyecta el runtime). El legacy
  `delete_staff_member` no tenía invariantes cruzados más allá de "ya terminado".
- Integración con `appointment.created` (listener declarado en `module.json` → `events.listen`):
  el legacy solo logueaba para trazabilidad/notificación. Si se materializa una reacción real
  (p.ej. marcar disponibilidad), iría a un handler; hoy es un no-op de notificación.
- Cross-módulo `services`: `staff_service.service_id` guarda una referencia **opaca** al id de
  un servicio de `services` (sin FK ni lectura de su tabla privada). El nombre se denormaliza en
  `service_name`. Cualquier resolución de servicios se hace vía query pública de `services`, no
  por JOIN cross-módulo.
