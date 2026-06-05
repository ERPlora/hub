-- Un informe de cumplimiento por id (scope hub_id). Portado de AuditService.get_report.
SELECT id, report_number, generated_at, generated_by_ref,
       period_start, period_end, filters, total_events, status, output_location
FROM audit_log_report
WHERE id = :report_id AND hub_id = :hub_id AND is_deleted = 0;
