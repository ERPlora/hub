-- Un proyecto por id (scope hub_id). Portado de GanttService.get_project (cabecera).
SELECT id, name, description, start_date, end_date, status, color,
       owner_ref, progress_pct, created_at
FROM gantt_project
WHERE id = :project_id AND hub_id = :hub_id AND is_deleted = 0;
