-- Lista de tareas del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de TaskService.list_tasks. Cada bind opcional usa la convención '' = sin filtro.
-- La validación de status/priority válidos la hace el SDK/UI; aquí solo se filtra.
SELECT id, task_number, title, description, project_id, status, priority,
       assigned_to_ref, created_by_ref, due_date, completed_at,
       parent_task_id, tags, created_at
FROM tasks_task
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status      = '' OR status          = :status)
  AND (:priority    = '' OR priority        = :priority)
  AND (:assigned_to = '' OR assigned_to_ref = :assigned_to)
  AND (:project_id  = '' OR project_id       = :project_id)
ORDER BY created_at DESC
LIMIT :limit;
