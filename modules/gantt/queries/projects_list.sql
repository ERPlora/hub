-- Lista de proyectos del hub con filtro opcional por estado. Runtime inyecta :hub_id.
-- Portado de GanttService.list_projects. (:status = '' → sin filtro.)
SELECT id, name, description, start_date, end_date, status, color,
       owner_ref, progress_pct, created_at
FROM gantt_project
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
