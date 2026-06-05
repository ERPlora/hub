-- Asientos contables del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de AccountingService.list_entries. Filtros: status, rango de fechas, límite.
-- (status '' = cualquier estado; start_date/end_date '' = sin cota.)
SELECT id, entry_number, entry_date, reference, description, status,
       total_debit, total_credit, posted_at, posted_by
FROM accounting_journal_entry
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:start_date = '' OR entry_date >= :start_date)
  AND (:end_date = '' OR entry_date <= :end_date)
ORDER BY entry_date DESC
LIMIT :limit;
