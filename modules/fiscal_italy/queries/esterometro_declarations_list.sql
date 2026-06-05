-- Declaraciones Esterometro del hub, filtro opcional por periodo.
-- Portado de ItFiscalService.list_esterometro (parte declarations). Runtime inyecta :hub_id.
-- (:period_year / :period_month: 0 = sin filtro.)
SELECT id, period_year, period_month, total_entries, submitted_at, submission_status
FROM fiscal_italy_esterometro_declaration
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:period_year = 0 OR period_year = :period_year)
  AND (:period_month = 0 OR period_month = :period_month)
ORDER BY created_at DESC;
