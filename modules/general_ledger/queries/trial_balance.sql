-- Balance de comprobación: cada cuenta activa con sus totales debe/haber acumulados.
-- Runtime inyecta :hub_id. Portado de GeneralLedgerService.get_trial_balance.
-- Solo apuntes de asientos 'posted'. Filtros opcionales por periodo (:period_id = '')
-- y por fecha tope (:as_of_date = '' → sin tope). LEFT JOIN para listar TODAS las
-- cuentas activas (incluso sin movimiento), preservando la estructura del plan.
-- El cuadre global (is_balanced) y el neto firmado por normal_balance los compone el SDK/UI;
-- aquí entregamos los agregados por cuenta.
SELECT a.id            AS account_id,
       a.code          AS code,
       a.name          AS name,
       a.account_type  AS account_type,
       a.normal_balance AS normal_balance,
       COALESCE(SUM(CASE WHEN e.id IS NOT NULL THEN l.debit  ELSE 0 END), 0) AS total_debit,
       COALESCE(SUM(CASE WHEN e.id IS NOT NULL THEN l.credit ELSE 0 END), 0) AS total_credit
FROM general_ledger_account a
LEFT JOIN general_ledger_line l
       ON l.account_id = a.id
      AND l.hub_id = a.hub_id
      AND l.is_deleted = 0
LEFT JOIN general_ledger_entry e
       ON e.id = l.entry_id
      AND e.hub_id = a.hub_id
      AND e.is_deleted = 0
      AND e.status = 'posted'
      AND (:period_id = '' OR e.period_id = :period_id)
      AND (:as_of_date = '' OR e.entry_date <= :as_of_date)
WHERE a.hub_id = :hub_id AND a.is_deleted = 0 AND a.is_active = 1
GROUP BY a.id, a.code, a.name, a.account_type, a.normal_balance
ORDER BY a.code ASC;
