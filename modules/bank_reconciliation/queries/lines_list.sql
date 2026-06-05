-- Líneas de un extracto (todas). Runtime inyecta :hub_id.
-- Portado de ReconciliationService.get_statement (sección include_lines).
SELECT id, statement_id, transaction_date, amount, description, counterparty,
       reference, is_matched, matched_at
FROM bank_reconciliation_line
WHERE hub_id = :hub_id AND is_deleted = 0 AND statement_id = :statement_id
ORDER BY transaction_date ASC;
