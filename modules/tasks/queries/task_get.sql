-- Detalle de una tarea por id. Runtime inyecta :hub_id.
-- Portado de TaskService.get_task (la cabecera). Los comentarios y subtareas se obtienen
-- con queries separadas (tasks.comments.list / tasks.subtasks.list) y los compone el SDK/UI.
SELECT id, task_number, title, description, project_id, status, priority,
       assigned_to_ref, created_by_ref, due_date, completed_at,
       parent_task_id, tags, created_at
FROM tasks_task
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :task_id;
