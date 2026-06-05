-- Una plantilla por id. Runtime inyecta :hub_id. Portado de
-- FinancialReportService.get_template (la carga de line_items la hace template_lines_list).
SELECT id, code, name, report_type, structure, is_default, is_active, created_at
FROM financial_statements_template
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :template_id
LIMIT 1;
