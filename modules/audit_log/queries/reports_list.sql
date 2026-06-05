-- Lista de informes de cumplimiento (más reciente primero), con filtro opcional por estado.
-- Portado de routes.list_reports. Runtime inyecta :hub_id. :status = '' = sin filtro.
SELECT id, report_number, generated_at, generated_by_ref,
       period_start, period_end, total_events, status, output_location
FROM audit_log_report
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY generated_at DESC
LIMIT :limit;
