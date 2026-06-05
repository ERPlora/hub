-- Un informe por id. Runtime inyecta :hub_id. Portado de ReportService.get_report.
SELECT id, code, name, description, report_type, data_source,
       filters, columns, groupings, sorts, is_public, schedule, owner_ref, created_at
FROM reports_report
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :report_id;
