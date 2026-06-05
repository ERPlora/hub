-- Líneas Esterometro del hub, filtro opcional por periodo.
-- Portado de ItFiscalService.list_esterometro (parte entries). Runtime inyecta :hub_id.
-- (:period_year / :period_month: 0 = sin filtro.)
SELECT id, period_year, period_month, transaction_type, counterparty_country,
       counterparty_vat_id, total_amount, transaction_date, document_ref, status
FROM fiscal_italy_esterometro_entry
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:period_year = 0 OR period_year = :period_year)
  AND (:period_month = 0 OR period_month = :period_month)
ORDER BY created_at DESC;
