-- Informes del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ReportService.list_reports. Los binds :report_type, :data_source y :owner_ref
-- deben pasarse: '' = sin filtro. is_public se filtra en SDK/UI si hace falta.
SELECT id, code, name, description, report_type, data_source,
       filters, columns, groupings, sorts, is_public, schedule, owner_ref, created_at
FROM reports_report
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:report_type = '' OR report_type = :report_type)
  AND (:data_source = '' OR data_source = :data_source)
  AND (:owner_ref   = '' OR owner_ref   = :owner_ref)
ORDER BY created_at DESC;
