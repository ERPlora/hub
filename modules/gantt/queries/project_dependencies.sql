-- Dependencias de un proyecto (vía sus tareas predecesoras). Runtime inyecta :hub_id.
-- Portado de GanttService.get_project (dependencies). Une dependencia→tarea para
-- filtrar por proyecto sin leer tablas de otros módulos (todo es gantt-propio).
SELECT d.id, d.predecessor_task_id, d.successor_task_id, d.dependency_type, d.lag_days
FROM gantt_task_dependency d
JOIN gantt_task t ON t.id = d.predecessor_task_id AND t.is_deleted = 0
WHERE d.hub_id = :hub_id AND d.is_deleted = 0
  AND t.project_id = :project_id
ORDER BY d.created_at ASC;
