-- Líneas (apuntes) de un asiento. Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.get_entry (sección lines).
SELECT id, entry_id, account_id, cost_center_id, debit, credit, description
FROM general_ledger_line
WHERE hub_id = :hub_id AND is_deleted = 0 AND entry_id = :entry_id
ORDER BY created_at ASC;
