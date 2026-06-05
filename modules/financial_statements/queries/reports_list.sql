-- Informes generados del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de FinancialReportService.list_reports. El filtro por periodo lo aplica el SDK
-- pasando :report_type (''=sin filtro), :period_start y :period_end ('' = sin filtro).
SELECT id, template_id, report_type, period_start, period_end,
       generated_at, generated_by_ref, status, notes, created_at
FROM financial_statements_generated
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:report_type = '' OR report_type = :report_type)
  AND (:period_start = '' OR period_start >= :period_start)
  AND (:period_end = '' OR period_end <= :period_end)
ORDER BY created_at DESC
LIMIT :limit;
