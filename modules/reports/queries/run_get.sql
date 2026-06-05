-- Una ejecución por id. Runtime inyecta :hub_id. Portado de ReportService.get_run.
SELECT id, report_id, run_number, filters_applied, started_at, completed_at,
       status, total_rows, output_format, output_location, run_by_ref, created_at
FROM reports_run
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :run_id;
