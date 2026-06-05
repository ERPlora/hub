# tasks — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_tasks/{models.py,services.py}`. El CRUD plano y las
mutaciones simples (asignar, comentar, crear proyecto) ya están en SQL declarativo
Tier 0 (`commands/{assign_task,add_comment,create_project}.sql`). Lo que sigue es
lógica de generación de secuencia atómica, validación de FKs y sellados condicionales
de estado que **no** cabe en una sola sentencia SQL y se convierte en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, valida/calcula y devuelve *intenciones* (filas a insertar/actualizar) que el
> runtime valida (permiso, hub_id, schema) y persiste dentro de una transacción. El reloj
> (`:now`), el `current_user_id` y el contador atómico son capacidades del host.

## 1. `create_task`  (command `tasks.tasks.create`)
Origen: `TaskService.create_task` + `generate_task_number`.
- Validar `title` no vacío (refuerzo; el JSON Schema ya exige `minLength: 1`).
- Validar `priority ∈ {low, medium, high, urgent}` (refuerzo del enum del schema).
- Parsear/validar `due_date`: acepta ISO `YYYY-MM-DD` o datetime completo; vacío/null → NULL.
  Normalizar a datetime UTC tz-aware (legacy `_parse_iso_datetime`).
- Validar FKs **del propio módulo** (mismo hub):
  - si `project_id` no es null → debe existir una fila viva en `tasks_project` (else error
    `project_not_found`). El runtime lo resuelve leyendo la tabla del módulo y pasando el
    resultado al WASM, o el WASM emite una lectura mediada; **no** es un import cruzado.
  - si `parent_task_id` no es null → debe existir una fila viva en `tasks_task`
    (else error `parent_not_found`).
- Generar `task_number` atómico → ver pieza 4 (counter). Formato `TSK-YYYYMMDD-NNNN`.
- Emitir intención de INSERT en `tasks_task` con: `status='todo'`, `priority`, `tags`
  (lista JSON, `[]` si vacía), `assigned_to_ref`/`created_by_ref`/`project_id`/`parent_task_id`
  (uuids o NULL), `due_date` normalizada, `completed_at=NULL`, contrato de auditoría estándar.
- Devolver `{id, task_number, title, status, priority}`.
- Emite evento `tasks.task.created`.

## 2. `update_status`  (command `tasks.tasks.update_status`)
Origen: `TaskService.update_status`.
- Validar `new_status ∈ {todo, in_progress, blocked, done, cancelled}` (refuerzo del enum).
- Leer la tarea (`task_id`, mismo hub, viva); si no existe → error `not_found`.
- Sellado condicional de `completed_at`:
  - si `new_status == 'done'` → `completed_at = :now`.
  - si el estado **previo** era `'done'` y el nuevo no lo es (reapertura) → `completed_at = NULL`.
  - en cualquier otro caso → `completed_at` se mantiene sin cambios.
- Emitir intención de UPDATE de `status` (+ `completed_at` según la regla) + auditoría
  (`updated_by`, `updated_at`).
- Devolver `{id, task_number, status, completed_at}`.
- Emite evento `tasks.task.status_changed`.
- No es un solo UPDATE porque `completed_at` depende del estado previo leído.

## 3. `complete_task`  (command `tasks.tasks.complete`)
Origen: `TaskService.complete_task`.
- Leer la tarea (`task_id`, mismo hub, viva); si no existe → error `not_found`.
- Guardas de estado:
  - si `status == 'done'` → error `already_done`.
  - si `status == 'cancelled'` → error `cancelled_locked` (no se puede completar una cancelada).
- Emitir intención de UPDATE: `status='done'`, `completed_at=:now` + auditoría.
- Devolver `{id, task_number, status, completed_at}`.
- Emite evento `tasks.task.completed`.
- Atajo de `update_status('done')` pero con guardas de estado adicionales → WASM.

## 4. Contador atómico de nº de tarea (`generate_task_number`)
Origen: `TaskCounter` + `generate_task_number` (UPSERT `INSERT ... ON CONFLICT (hub_id, day)
DO UPDATE SET last_number = last_number + 1 RETURNING last_number`). Formato
`TSK-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- En hub-next se resuelve como capacidad del runtime (counter UPSERT sobre `tasks_counter`)
  invocada por el handler `create_task`; el WASM solo formatea `TSK-{day}-{n:04d}` con el
  número devuelto. La UniqueConstraint `tasks_task(hub_id, task_number)` es la guarda final.

## 5. `get_my_tasks` — nota (query, NO command)
Origen: `TaskService.get_my_tasks`. Mayormente resuelto en `queries/my_tasks.sql` (Tier 0):
el SDK calcula `due_horizon = ahora + due_within_days` y pasa `apply_horizon` (1 si
`due_within_days > 0`, 0 si no). El orden `due_date ASC nullslast` del legacy se aproxima con
`ORDER BY due_date ASC` (las filas sin fecha solo aparecen cuando `apply_horizon = 0`, donde
SQLite ordena NULL primero). Si se exige el *nullslast* exacto del legacy en el caso sin
horizonte, moverlo a un pequeño post-orden en el SDK o a un handler — no bloqueante.
