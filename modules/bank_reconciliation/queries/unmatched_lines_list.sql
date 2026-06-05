-- Líneas aún sin conciliar (opcionalmente acotadas a un extracto). Runtime inyecta :hub_id.
-- Portado de ReconciliationService.list_unmatched_lines. El bind :statement_id puede ser
-- '' = todas las líneas no conciliadas del hub.
SELECT id, statement_id, transaction_date, amount, description, counterparty,
       reference, is_matched, matched_at
FROM bank_reconciliation_line
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_matched = 0
  AND (:statement_id = '' OR statement_id = :statement_id)
ORDER BY transaction_date ASC
LIMIT :limit;
