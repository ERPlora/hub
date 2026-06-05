-- Un asiento por id (scope hub_id). Portado de AccountingService.get_entry (cabecera).
-- Las líneas se piden aparte con accounting.lines.by_entry.
SELECT id, entry_number, entry_date, reference, description, status,
       total_debit, total_credit, posted_at, posted_by
FROM accounting_journal_entry
WHERE id = :entry_id AND hub_id = :hub_id AND is_deleted = 0;
