-- Asientos del libro mayor con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.list_entries (filtros status / period_id).
-- El filtro por account_id (entradas que tocan una cuenta) se resuelve mejor vía
-- general_ledger.accounts.movements; aquí filtramos cabeceras directamente.
SELECT id, entry_number, entry_date, period_id, reference, description,
       status, total_debit, total_credit, posted_at
FROM general_ledger_entry
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:period_id = '' OR period_id = :period_id)
ORDER BY entry_date DESC
LIMIT :limit;
