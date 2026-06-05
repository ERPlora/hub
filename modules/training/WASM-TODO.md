# training — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_training/{models.py,services.py,routes.py}`. El CRUD plano
(programas, habilidades, asignación/actualización/borrado de competencias de empleado) ya
está en SQL declarativo Tier 0 (`commands/*.sql`). Lo que sigue es lógica de validación,
guardas de estado, comprobación de capacidad/dependencias y upsert de singleton que **no**
cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el runtime
> lea (por queries declarativas) y devuelve *intenciones* (filas a insertar/actualizar/borrar,
> sub-comandos a ejecutar) que el runtime valida y persiste en una transacción.

## 1. `delete_program`  (command `training.programs.delete`)
Origen: `ProgramService.delete_program`.
- Leer el programa por `program_id` (+ `hub_id`); si no existe → error `not_found`.
- Leer sus inscripciones (`training_employee_training` WHERE `program_id`, `is_deleted=0`).
- **Guarda**: si hay inscripciones con `status IN ('not_started','in_progress')` → error
  `has_active_enrollments` con `{active_enrollments: N}` (no se borra; cancelar/completar primero).
- Si no hay activas: soft-delete del programa (`is_deleted=1`, `is_active=0`, `deleted_at=now`,
  `updated_by/updated_at`). Conserva histórico de inscripciones pasadas que apuntan al FK.
- Emitir `training.program.deleted` con `{program_id, name}`.

## 1b. `delete_skill`  (command `training.skills.delete`)
Origen: `SkillService.delete_skill`. Schema: `schemas/skill_delete.json`.
- Leer la habilidad por `skill_id` (+ `hub_id`); si no existe → error `not_found`.
- **Guarda de dependencia**: contar filas activas en `training_employee_skill`
  (WHERE `skill_id`, `is_deleted=0`) que referencian la habilidad; si hay > 0 →
  error `has_active_competencies` con `{active: N}` (no se borra: reasignar/retirar
  esas competencias de empleado primero).
- Si no hay competencias activas: soft-delete de la habilidad (`is_deleted=1`,
  `deleted_at=now`, `updated_by/updated_at`). Conserva histórico que apunte al FK.
- Emitir `training.skill.deleted` con `{skill_id, name}`.

## 2. `enroll_employee`  (command `training.enrollments.enroll`)
Origen: `EnrollmentService.enroll_employee`.
- Leer el programa por `program_id`; si no existe → error `not_found`.
- **Guarda**: si `is_active = 0` → error `inactive`.
- **Guarda de capacidad**: si `max_participants > 0`, contar inscripciones activas no borradas
  del programa (`enrolled_count`); si `enrolled_count >= max_participants` → error `full`.
- **Guarda de duplicado**: si ya existe una inscripción de ese `employee_id` en ese programa con
  `status NOT IN ('failed','expired')` → error `already_enrolled`.
- `employee_id` referencia a un `StaffMember` del módulo `staff` — NO se hace SELECT directo a
  tablas de staff. La existencia del empleado se valida vía contrato (query pública
  `staff.members.get`) o se confía en el `employee_name` que pasa la UI. El nombre llega ya
  resuelto en el payload (`employee_name`).
- Si pasa: insertar `training_employee_training` con `status='not_started'` (resto NULL/'').
- Emitir `training.enrollment.created` con `{id, program, enrolled:true}`.

## 3. `update_training_status`  (command `training.enrollments.update_status`)
Origen: `EnrollmentService.update_training_status`.
- Leer la inscripción por `enrollment_id`; si no existe → error `not_found`.
- **Guarda de nota de corte** (legacy referencia `program.min_passing_score`, que no existe en
  el modelo actual — dejar como hook futuro): si `status='completed'` y `score` por debajo del
  mínimo de aprobado del programa → error `below_passing`. Hoy no aplica (no hay campo);
  documentado por si se reintroduce `min_passing_score` en `training_program`.
- Aplicar: `status` nuevo; si `status='completed'` y `completion_date` está vacío → fijar a hoy
  (capacidad "reloj" del host); si `score` no nulo → fijarlo. `updated_by/updated_at`.
- Emitir `training.enrollment.updated` con `{id, status, updated:true}`.

## 4. `save_settings`  (command `training.settings.save`)
Origen: `_get_settings` + `settings_save` (creación lazy del singleton + actualización parcial).
- Singleton por `hub_id`: si no existe fila en `training_settings` para el hub → INSERT con
  `new_id` y los valores (o defaults: `require_completion_proof=0`, `auto_assign_mandatory=1`,
  `reminder_days_before=7`, `certificate_expiry_warning_days=30`).
- Si existe → UPDATE de los campos presentes en el payload (actualización parcial; los ausentes
  no se tocan), con `updated_by/updated_at`.
- No se puede expresar como una sola sentencia (UPSERT con `id` generado solo en INSERT +
  actualización parcial selectiva) → WASM decide INSERT vs UPDATE leyendo primero la fila.
- Emitir `training.settings.updated`.

## 5. Listener de evento `staff.member_created`  (events.listen)
Origen: TODO documentado en `events.py` ("auto-assign mandatory trainings").
- Cuando llega `staff.member_created` con `{employee_id, employee_name}`: si la config del hub
  tiene `auto_assign_mandatory=1`, leer los programas `is_mandatory=1, is_active=1` del hub y
  auto-inscribir al empleado en cada uno (reutilizando la lógica de `enroll_employee`, pieza 2,
  saltando los ya inscritos por la guarda de duplicado).
- Cross-módulo vía contrato de eventos: training **no** importa de staff; consume el evento que
  staff emite y solo lee/escribe sus propias tablas (`training_*`).
- Pendiente de cablear como handler de evento (Tier 2) cuando el runtime soporte handlers de
  evento que emitan sub-comandos.

## 6. Agregados de listado (NO bloqueante — Tier 0/UI)
Origen: propiedades `enrolled_count` / `completed_count` / `completion_rate` (TrainingProgram) y
`employee_count` (Skill).
- El listado legacy adjuntaba estos contadores a cada fila. En hub-next se resuelven con queries
  agregadas separadas o se calculan en la UI a partir de `training.enrollments.list`; no se
  necesita WASM. Si se quiere el conteo embebido por fila en una sola query, conviene una vista
  o subconsulta correlacionada — pero queda fuera del MVP de migración (la UI agrega).

## 7. Matriz de habilidades (Tier 0 + UI)
Origen: `skills_matrix`.
- La query `training.skills_matrix.list` devuelve las filas planas empleado×habilidad; el WC
  las pivota a la rejilla `{employee_id: {skill_id: proficiency_level}}`. Sin WASM.
