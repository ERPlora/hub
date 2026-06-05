-- Un informe generado por id, incluyendo su snapshot data. Runtime inyecta :hub_id.
-- Portado de FinancialReportService.get_report.
SELECT id, template_id, report_type, period_start, period_end,
       generated_at, generated_by_ref, status, data, notes, created_at
FROM financial_statements_generated
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :report_id
LIMIT 1;
