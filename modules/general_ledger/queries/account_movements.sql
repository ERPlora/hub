-- Movimientos (apuntes) posteados que tocan una cuenta. Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.get_account_movements. Solo asientos 'posted'.
-- Filtro opcional por periodo (:period_id = '' → todos). Incluye eje de centro de coste.
SELECT l.id           AS line_id,
       e.id           AS entry_id,
       e.entry_number AS entry_number,
       e.entry_date   AS entry_date,
       e.reference    AS reference,
       l.debit        AS debit,
       l.credit       AS credit,
       l.cost_center_id AS cost_center_id,
       l.description  AS description
FROM general_ledger_line l
JOIN general_ledger_entry e ON e.id = l.entry_id AND e.hub_id = l.hub_id
WHERE l.hub_id = :hub_id AND l.is_deleted = 0
  AND e.is_deleted = 0 AND e.status = 'posted'
  AND l.account_id = :account_id
  AND (:period_id = '' OR e.period_id = :period_id)
ORDER BY e.entry_date DESC
LIMIT :limit;
