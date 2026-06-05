-- Métricas agregadas de un proyecto: nº tareas, completadas, hitos y vencidas.
-- Runtime inyecta :hub_id y :today (ISO YYYY-MM-DD). Portado de GanttService.get_project_summary.
SELECT
    COUNT(*)                                                            AS total_tasks,
    COALESCE(SUM(CASE WHEN progress_pct >= 100 THEN 1 ELSE 0 END), 0)   AS completed,
    COALESCE(SUM(CASE WHEN is_milestone = 1 THEN 1 ELSE 0 END), 0)      AS milestones,
    COALESCE(SUM(CASE WHEN end_date IS NOT NULL AND end_date < :today
                       AND progress_pct < 100 THEN 1 ELSE 0 END), 0)    AS overdue
FROM gantt_task
WHERE hub_id = :hub_id AND is_deleted = 0
  AND project_id = :project_id;
