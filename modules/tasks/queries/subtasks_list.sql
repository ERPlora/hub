-- Subtareas de una tarea (hijas por parent_task_id). Runtime inyecta :hub_id.
-- Portado de la rama include_subtasks de TaskService.get_task.
SELECT id, task_number, title, description, project_id, status, priority,
       assigned_to_ref, created_by_ref, due_date, completed_at,
       parent_task_id, tags, created_at
FROM tasks_task
WHERE hub_id = :hub_id AND is_deleted = 0 AND parent_task_id = :task_id
ORDER BY created_at ASC;
