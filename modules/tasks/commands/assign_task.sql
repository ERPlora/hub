-- Asigna (o desasigna con :assigned_to_ref = NULL) una tarea. Runtime inyecta
-- :hub_id, :current_user_id, :now. Portado de TaskService.assign_task.
UPDATE tasks_task
SET assigned_to_ref = :assigned_to_ref,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :task_id AND hub_id = :hub_id AND is_deleted = 0;
