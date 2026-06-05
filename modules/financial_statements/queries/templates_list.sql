-- Plantillas de informe del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de FinancialReportService.list_templates.
-- :report_type = '' → sin filtro de tipo. :active_only = 1 → solo activas, 0 → todas.
SELECT id, code, name, report_type, structure, is_default, is_active, created_at
FROM financial_statements_template
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:report_type = '' OR report_type = :report_type)
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
