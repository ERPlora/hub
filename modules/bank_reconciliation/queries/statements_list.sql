-- Lista de extractos bancarios del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ReconciliationService.list_statements. Los binds :status y :bank_account_ref
-- deben pasarse: '' = sin filtro.
SELECT id, statement_number, bank_account_ref, statement_date, period_start, period_end,
       opening_balance, closing_balance, status, notes, created_at
FROM bank_reconciliation_statement
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:bank_account_ref = '' OR bank_account_ref = :bank_account_ref)
ORDER BY created_at DESC
LIMIT :limit;
