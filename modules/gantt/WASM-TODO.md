# gantt — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_gantt/{models.py,services.py}`. El CRUD plano (alta de
proyecto) ya está en SQL declarativo Tier 0 (`commands/project_create.sql`) y las
lecturas en `queries/*.sql`. Lo que sigue es lógica de validación cruzada / cálculo /
propagación / grafo que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos a
> ejecutar) que el runtime valida y persiste en una transacción. Las fechas son ISO
> `YYYY-MM-DD`; la aritmética de fechas usa días naturales (`timedelta(days=...)`).

---

## 1. `add_task`  (command `gantt.tasks.add`)
Origen: `GanttService.add_task` + `GanttTask.recompute_duration`.

El runtime lee y entrega al WASM:
- El proyecto destino `project_id` (debe existir y pertenecer al hub → si no, error `project_not_found`).
- Si viene `parent_task_id`: la tarea padre (debe existir; **debe** pertenecer al
  mismo proyecto → si no, error `parent_project_mismatch` / `parent_not_found`).

Lógica:
- `name` no vacío (ya cubierto por el schema).
- Validar/normalizar `assigned_to_ref` y `parent_task_id` como UUID (vacío → NULL).
- **Cálculo de duración** (`recompute_duration`):
  - Si `is_milestone` → `duration_days = 0`.
  - Si `start_date` y `end_date` presentes → `duration_days = max(0, (end - start).days)`.
  - Si faltan fechas → `duration_days = 0` (no se computa).
- Devolver la intención de `INSERT` en `gantt_task` con todos los campos
  (incl. `duration_days` calculado, `order`, contrato hub_id/auditoría inyectado por runtime).
- Emitir `gantt.task.created`.
- Respuesta: `{id, name, project_id, duration_days, is_milestone}`.

## 2. `add_dependency`  (command `gantt.dependencies.add`)
Origen: `GanttService.add_dependency`.

El runtime lee y entrega: la tarea predecesora y la sucesora (ambas deben existir).

Lógica de validación (toda no-SQL, requiere ver ambas filas):
- `dependency_type` ∈ {finish_to_start, start_to_start, finish_to_finish, start_to_finish}
  (ya cubierto por el schema).
- `predecessor_task_id != successor_task_id` → si no, error `self_dependency`.
- `predecessor.project_id == successor.project_id` → si no, error `cross_project`
  ("Both tasks must belong to the same project").
- Devolver intención de `INSERT` en `gantt_task_dependency` (con `lag_days`, hub_id/auditoría).
- Emitir `gantt.dependency.created`.
- Respuesta: `{id, predecessor_task_id, successor_task_id, dependency_type, lag_days}`.

> Nota: una protección contra ciclos NO está en el legacy (el grafo se asume acíclico por
> uso). El cálculo de camino crítico (pieza 6) degrada con elegancia si hay ciclo, así que
> no es bloqueante; opcional añadir detección de ciclo aquí más adelante.

## 3. `update_task_progress`  (command `gantt.tasks.update_progress`)
Origen: `GanttService.update_task_progress`.

Es **batch + agregación**, no una sola UPDATE: tras fijar el progreso de la tarea hay que
recalcular el progreso agregado del proyecto.

El runtime lee y entrega: la tarea objetivo + **todas** las tareas hermanas del mismo
`project_id` (para promediar) + el proyecto.

Lógica:
- `progress_pct` entero 0-100 (ya cubierto por el schema; el legacy lo revalida → mantener
  errores `invalid_progress` / `out_of_range` como defensa).
- Fijar `task.progress_pct = progress` (intención UPDATE sobre la tarea).
- `project_progress = floor(Σ task.progress_pct / nº tareas)` (media entera; 0 si no hay tareas).
  Incluye la tarea recién actualizada en la media.
- Fijar `project.progress_pct = project_progress` (intención UPDATE sobre el proyecto).
- Emitir `gantt.task.progress_updated`.
- Respuesta: `{id, progress_pct, project_progress_pct}`.

## 4. `shift_task`  (command `gantt.tasks.shift`)
Origen: `GanttService.shift_task` + `_shift` + `_apply_dependency`.

Es el más complejo: **propagación de fechas por el grafo de dependencias (BFS)**.

El runtime lee y entrega: la tarea raíz `task_id` + **todas** las tareas del mismo proyecto
+ **todas** las dependencias del proyecto (indexadas por predecesor).

Lógica:
- Desplazar la tarea raíz: a `start_date` y `end_date` (cada una si no es NULL) sumarles
  `days_delta` días (`_shift`). `days_delta` puede ser negativo.
- BFS desde la raíz; por cada dependencia saliente `(pred → succ)` aplicar la restricción
  según `dependency_type` (`_apply_dependency`), que solo actúa si las fechas implicadas
  existen y la restricción está violada (mover **solo hacia delante**, nunca adelantar):
  - **finish_to_start (FS)**: `succ.start >= pred.end + lag`. Si `succ.start < target`,
    desplazar succ por `(target - succ.start).days`.
  - **start_to_start (SS)**: `succ.start >= pred.start + lag`. Igual sobre `succ.start`.
  - **finish_to_finish (FF)**: `succ.end >= pred.end + lag`. Desplazar por `(target - succ.end).days`.
  - **start_to_finish (SF)**: `succ.end >= pred.start + lag` (raro). Desplazar por `(target - succ.end).days`.
  - "Desplazar succ" = `_shift(succ, delta)` → mueve **ambas** fechas de succ por ese delta.
  - Si una tarea fue movida, encolar su id para propagar a sus propios sucesores (marcar visitados).
- Devolver una intención UPDATE por cada tarea cuyas fechas cambiaron (start/end nuevos).
- Emitir `gantt.task.shifted`.
- Respuesta: `{task_id, days_delta, affected:[ids...]}` (lista de tareas tocadas, incl. la raíz).

> Cuidado de portabilidad: el legacy usa `defaultdict(list)` + `deque` para BFS. En Rust es
> un `HashMap<TaskId, Vec<Dep>>` + `VecDeque`. La media-aritmética entera de la pieza 3 es
> truncada (floor), replicar `//` de Python.

## 5. (reservado) recompute_duration en edición de tareas
Origen: `GanttTask.recompute_duration`. Hoy solo se usa en `add_task` (pieza 1). Si en el
futuro se añade un `update_task` que cambie fechas/hito, debe re-llamar a la misma lógica
de la pieza 1 (duración derivada de start/end, 0 para hitos). No hay command para ello aún
→ NO se ha declarado en `module.json` (sin nav/command muerto).

## 6. `calculate_critical_path`  (command/lectura `gantt.projects.critical_path`)
Origen: `GanttService.calculate_critical_path`.

Es de **solo lectura** (no muta), pero es un algoritmo de grafo (longest-path) que no cabe
en SQL → handler WASM con permiso `gantt.view_gantt` (sin `transaction`).

El runtime lee y entrega: el proyecto + todas sus tareas + todas sus dependencias.

Lógica (algoritmo simplificado del legacy):
- Si el proyecto no tiene tareas → `{ok:true, project_id, path:[]}`.
- Construir DAG: `incoming[succ] += dep`, `outgoing[pred] += dep` (cualquier tipo de
  dependencia se trata como arista FS para el longest-path).
- **Orden topológico (Kahn)** por indegree. Si `len(topo) != nº tareas` (hay ciclo) →
  degradar a `topo = task_ids` (orden de inserción) sin romper.
- **Longest-path (DP)** sobre el orden topo:
  - `best[t] = max sobre deps entrantes de (best[pred] + lag) ` + `duration_days[t]`;
    `best_in = 0` si no hay entrantes. Guardar `prev[t] = pred` del mejor candidato.
- `end_id = argmax(best)`; reconstruir `path` siguiendo `prev` hacia atrás y revertir.
- Respuesta: `{ok:true, project_id, path:[task_ids...], total_duration_days: best[end_id]}`.

> Nota: `lag_days` participa en la suma del camino; `duration_days` de cada tarea es el peso
> del nodo. Replicar exactamente el DP del legacy (líneas 563-592 de services.py).

---

## Resumen de funciones WASM a implementar
| función               | command                         | muta | lee del runtime                                  |
|-----------------------|---------------------------------|------|--------------------------------------------------|
| `add_task`            | `gantt.tasks.add`               | sí   | proyecto + (opcional) tarea padre                |
| `add_dependency`      | `gantt.dependencies.add`        | sí   | tarea predecesora + sucesora                     |
| `update_task_progress`| `gantt.tasks.update_progress`   | sí   | tarea + hermanas del proyecto + proyecto         |
| `shift_task`          | `gantt.tasks.shift`             | sí   | raíz + todas las tareas + todas las dependencias |
| `calculate_critical_path` | `gantt.projects.critical_path` | no | proyecto + todas las tareas + todas las deps    |

CRUD/lecturas ya en Tier 0 (no WASM): `gantt.projects.create` (SQL), `gantt.projects.list`,
`gantt.projects.get`, `gantt.projects.tasks`, `gantt.projects.dependencies`,
`gantt.projects.summary` (agregación expresable en SQL puro).
