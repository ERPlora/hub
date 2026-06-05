-- Ejecuciones recientes (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ReportService.list_runs. Binds :report_id y :status: '' = sin filtro.
SELECT id, report_id, run_number, filters_applied, started_at, completed_at,
       status, total_rows, output_format, output_location, run_by_ref, created_at
FROM reports_run
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:report_id = '' OR report_id = :report_id)
  AND (:status    = '' OR status    = :status)
ORDER BY created_at DESC;
