-- Líneas (apuntes) de un asiento (scope hub_id). Portado de AccountingService.get_entry (lines).
SELECT id, entry_id, account_id, debit, credit, description
FROM accounting_journal_line
WHERE entry_id = :entry_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
