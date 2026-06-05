-- Comentarios de una tarea, en orden cronológico. Runtime inyecta :hub_id.
-- Portado de la rama include_comments de TaskService.get_task.
SELECT id, task_id, author_ref, comment, created_at
FROM tasks_comment
WHERE hub_id = :hub_id AND is_deleted = 0 AND task_id = :task_id
ORDER BY created_at ASC;
