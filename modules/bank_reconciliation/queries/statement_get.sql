-- Detalle de un extracto bancario concreto. Runtime inyecta :hub_id.
-- Portado de ReconciliationService.get_statement (la cabecera; las líneas se piden por
-- separado con bank_reconciliation.lines.list).
SELECT id, statement_number, bank_account_ref, statement_date, period_start, period_end,
       opening_balance, closing_balance, status, notes, created_at
FROM bank_reconciliation_statement
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :statement_id;
