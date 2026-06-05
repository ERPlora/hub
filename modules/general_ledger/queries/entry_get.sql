-- Cabecera de un asiento concreto. Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.get_entry (cabecera). Las líneas se piden aparte
-- vía general_ledger.entries.lines.
SELECT id, entry_number, entry_date, period_id, reference, description,
       status, total_debit, total_credit, posted_at
FROM general_ledger_entry
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :entry_id;
