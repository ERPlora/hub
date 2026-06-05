-- Tareas de un proyecto, ordenadas por order y fecha de alta. Runtime inyecta :hub_id.
-- Portado de GanttService.get_project (tareas). Sirve también a la vista timeline.
SELECT id, project_id, name, start_date, end_date, duration_days,
       assigned_to_ref, progress_pct, is_milestone, parent_task_id, "order"
FROM gantt_task
WHERE hub_id = :hub_id AND is_deleted = 0
  AND project_id = :project_id
ORDER BY "order" ASC, created_at ASC;
