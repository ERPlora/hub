-- Tareas abiertas asignadas a un usuario, opcionalmente acotadas por horizonte de vencimiento.
-- Runtime inyecta :hub_id. Portado de TaskService.get_my_tasks.
-- "Abiertas" excluye done y cancelled. El SDK calcula :due_horizon (ISO datetime = ahora +
-- due_within_days) y pasa :apply_horizon = 1 cuando due_within_days > 0, 0 en caso contrario.
-- Con horizonte activo solo se incluyen tareas CON due_date <= horizonte (las sin fecha se
-- excluyen, igual que el legacy con due_within_days > 0).
SELECT id, task_number, title, description, project_id, status, priority,
       assigned_to_ref, created_by_ref, due_date, completed_at,
       parent_task_id, tags, created_at
FROM tasks_task
WHERE hub_id = :hub_id AND is_deleted = 0
  AND assigned_to_ref = :assigned_to_ref
  AND status NOT IN ('done', 'cancelled')
  AND (:apply_horizon = 0 OR (due_date IS NOT NULL AND due_date <= :due_horizon))
ORDER BY due_date ASC;
