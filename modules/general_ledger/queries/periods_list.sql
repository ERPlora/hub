-- Periodos contables del hub. Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.list_periods. Filtro opcional por status ('' = todos).
SELECT id, name, start_date, end_date, status, closed_at
FROM general_ledger_period
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY start_date ASC;
