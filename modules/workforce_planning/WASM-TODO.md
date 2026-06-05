# workforce_planning — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_workforce_planning/{models.py,services.py}`. El CRUD plano
(sedes, plantillas de turno, calendario laboral, requisitos de cobertura) ya está en SQL
declarativo Tier 0 (`commands/*.sql`). Lo que sigue es lógica de **cálculo / detección de
conflictos / batch / agregación temporal** que NO cabe en una sola sentencia SQL y debe
convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas que el runtime
> lee por él (asignaciones, ajustes, calendario, cobertura), calcula y devuelve *intenciones*
> (filas a insertar/actualizar, comandos a ejecutar) que el runtime valida y persiste en una
> transacción. Las horas se calculan en minutos enteros; los importes con `quantize(0.01)`.

---

## 1. `create_shift_assignment`  (command `workforce_planning.assignments.create`)  ⟵ ÚNICO handler WASM declarado
Origen: `PlanningService.create_shift_assignment` + `detect_conflicts` + `check_overtime` +
`check_rest_period`. Es el corazón del módulo: inserta una asignación SOLO tras detectar
conflictos, y si hay bloqueantes y `force=false`, **rechaza** sin insertar.

**Binds que el runtime debe proveer al WASM** (lecturas previas, scoped por `hub_id`):
- `payload`: `{employee_id, employee_name, location_id, date, start_time(HH:MM), end_time(HH:MM),
  shift_template_id?, break_minutes, notes, force}` (validado contra `schemas/assignment_create.json`).
- `settings`: fila de `workforce_planning_settings` del hub (o defaults:
  `overtime_weekly_threshold=40`, `min_rest_hours_between_shifts=11`, `auto_detect_conflicts=true`).
- `same_day`: asignaciones del MISMO `employee_id` en `date` con `status IN (scheduled,confirmed)`.
- `week`: asignaciones del MISMO `employee_id` con `date` en la semana ISO de `date`
  (lunes..domingo) y `status IN (scheduled,confirmed,completed)` — para horas extra.
- `prev_day`: última asignación (mayor `end_time`) del MISMO `employee_id` el día anterior
  con `status IN (scheduled,confirmed,completed)` — para descanso entre turnos.

**Lógica (portar exactamente de `services.py`):**
1. **Duración de turno** (`duration_hours`): `start_min = h*60+m`; `end_min = h*60+m`;
   si `end_min <= start_min` → `end_min += 1440` (turno nocturno); `dur = (end_min - start_min - break_minutes)/60`.
2. **Doble reserva** (`double_booking`): para cada fila de `same_day`, comprobar solape de
   rangos `_times_overlap` (con wrap nocturno: si `end<=start`, sumar 1440 a ambos lados):
   `a_start < b_end && b_start < a_end`. Mensaje:
   `"Overlaps with existing shift at HH:MM-HH:MM (<location.name>)"`.
3. **Horas extra** (`overtime`): `total = Σ duration_hours(week) + duration_hours(nuevo turno)`;
   si `total > settings.overtime_weekly_threshold` → conflicto. (En el legacy `check_overtime`
   suma solo las existentes; al crear, sumar también el turno propuesto para detectar el cruce.)
   Mensaje: `"Weekly hours (X.Yh) exceed threshold (Nh)"`.
4. **Descanso insuficiente** (`insufficient_rest`): si hay `prev_day`,
   `gap_h = (combine(date, start_time) - combine(prev_date, prev_end)).hours`;
   si `gap_h < settings.min_rest_hours_between_shifts` → conflicto. Sin `prev_day` → suficiente (24h).
   Mensaje: `"Only X.Yh rest between shifts (minimum Nh required)"`.
5. **Conflictos bloqueantes** = `{double_booking, insufficient_rest}` (overtime es solo aviso).
   Si hay bloqueantes y `force=false` → devolver SIN insertar:
   `{error:"Shift assignment blocked due to scheduling conflicts", blocking_conflicts:[{type,message}], hint:"Use force=true to override blocking conflicts"}`.
6. Si OK (o `force=true`): emitir intención de **insertar la asignación**
   (`workforce_planning_shift_assignment`, `status='scheduled'`) y, por cada conflicto detectado
   (bloqueante o no), una intención de **insertar un `workforce_planning_conflict`**
   (`employee_id, employee_name, conflict_type, date, details=message, shift_assignment_id=<nuevo>`).
   El runtime persiste todo en UNA transacción y luego emite `workforce_planning.assignment.created`.
   Devolver `{id, created:true, forced: force && había_bloqueantes, conflicts:[{type,message}]}`.

> Nota: requiere que el runtime cree la asignación primero (para tener su id) y luego inserte
> los conflictos enlazados — el WASM devuelve las dos intenciones y el orden; el runtime resuelve
> el `shift_assignment_id` del conflicto con el id recién generado.

---

## 2. Detección de conflictos / horas extra / descanso como queries de solo lectura (futuro)
Origen: `check_overtime`, `check_rest_period`, `PlanningService.check_employee_overtime`,
`get_unresolved_conflicts`. Hoy:
- `get_unresolved_conflicts` ya está cubierto por la query Tier 0 `conflicts.unresolved`.
- `check_employee_overtime` (solo lectura: ¿supera el umbral semanal?) NO se ha expuesto como
  command porque es agregación temporal (suma de `duration_hours` por semana ISO). Si se quiere
  como acción consultable, va a un handler WASM `check_overtime(employee_id, date)` que reciba
  las asignaciones de la semana (binds como en §1.week) y devuelva `{total_hours, threshold, exceeded}`.
  Sin command declarado todavía (no añadir nav muerta).

---

## 3. `check_coverage_gaps`  (futuro — análisis de huecos de cobertura)
Origen: `PlanningService.check_coverage_gaps` + `check_coverage`.
- Cruza `coverage_requirement` (filtrados por `location_id`, `day_of_week == weekday(date) OR NULL`,
  `is_active`) contra el conteo de asignaciones reales de esa sede/fecha (opcionalmente por
  `shift_template_id`), con `status IN (scheduled,confirmed)`.
- Por requisito: `gap = max(0, min_employees - assigned)`. Devuelve
  `{date, coverage:[{shift_template, required, assigned, gap, role_required, day_of_week}], has_gaps}`.
- Requiere conteo agregado + join lógico en memoria → handler WASM (binds: requirements + counts).
  No declarado como command todavía (la vista Coverage solo lista requisitos via Tier 0).

---

## 4. `calculate_shift_cost`  (futuro — coste estimado de turno)
Origen: `calculate_shift_cost`.
- Lee la entrada de `labor_calendar` de la fecha (`pay_multiplier`, default 1.00 si no hay festivo),
  el resultado de horas extra (§1/§2) y `settings.overtime_weekly_threshold`.
- `overtime_hours = max(0, total_week_hours - threshold)`;
  `regular_hours = base_hours - overtime_hours` (0 si overtime ≥ base).
- `coste = regular*rate*holiday_mult + overtime*rate*1.5*holiday_mult`.
- Devuelve `{base_hours, overtime_hours, holiday_multiplier, estimated_cost, is_holiday, holiday_name}`.
- Cálculo decimal con multiplicadores → handler WASM. No declarado todavía.

---

## 5. `import_spanish_holidays`  (futuro — import batch de festivos)
Origen: `get_spanish_holidays` + `_compute_easter` + `ImportHolidaysRequest`.
- Genera festivos nacionales fijos + Viernes Santo (algoritmo de Pascua Gregoriano anónimo) +
  festivos regionales por comunidad (`ES-MD`, `ES-CT`, `ES-AN`, `ES-VC`, `ES-PV`, `ES-GA`,
  `ES-AR`, `ES-IB`, `ES-CN`) para un `year` (y `region` opcional; `None` = todas).
- Devuelve N intenciones de insertar en `workforce_planning_labor_calendar`
  (`calendar_type='public_holiday'|'regional_holiday'`, `pay_multiplier=2.00`), respetando el
  uq `(hub_id, date, calendar_type, region)` (upsert / skip duplicados — capacidad del runtime).
- Lógica de fechas + algoritmo de Pascua + tabla regional → handler WASM. Operación batch sobre
  ~15-20 filas. No declarado como command todavía (alta manual disponible via `calendar.create`).

---

## 6. Validación de skills al asignar  (futuro — cross-módulo `training`)
Origen: `validate_shift_skills` (lazy import de `training.models.EmployeeSkill`).
- Comprueba que el empleado tiene TODAS las `required_skills` (JSON array) de la plantilla de turno.
- **Cross-módulo PROHIBIDO por import**: en hub-next NO se hace lazy import de `training`. Debe
  resolverse vía **contrato público**: el runtime/handler consulta una query pública del módulo
  `training` (p.ej. `training.employee_skills.list?employee_id=`) y el WASM compara nombres
  (case-insensitive). Fail-open si `training` no está instalado (devuelve `(ok=true, missing=[])`),
  igual que el legacy. Integrar en §1 (`create_shift_assignment`) como guarda adicional opcional
  cuando la plantilla tenga `required_skills` no vacío. No declarado todavía.

---

## Resumen de handlers
| Estado | Función WASM | Command |
|--------|--------------|---------|
| **Declarado** | `create_shift_assignment` (§1) | `workforce_planning.assignments.create` |
| Futuro | `check_overtime` (§2) | — (no expuesto) |
| Futuro | `check_coverage_gaps` (§3) | — |
| Futuro | `calculate_shift_cost` (§4) | — |
| Futuro | `import_spanish_holidays` (§5) | — |
| Futuro | `validate_shift_skills` (§6, vía contrato `training`) | guarda de §1 |
