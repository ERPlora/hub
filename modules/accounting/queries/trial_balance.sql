-- Balance de comprobación: toda cuenta activa con sus totales de débito/crédito
-- provenientes SOLO de asientos contabilizados (status='posted'). Runtime inyecta :hub_id.
-- Portado de AccountingService.get_trial_balance. Incluye cuentas sin actividad (LEFT JOIN
-- a la subconsulta agregada) para que la estructura del plan sea visible.
-- Cota opcional :end_date ('' = sin cota). JOIN entre tablas PROPIAS del módulo (permitido).
-- El cálculo del 'net' por normal_balance y el flag is_balanced agregado los hace el UI/SDK.
SELECT a.id             AS account_id,
       a.code           AS code,
       a.name           AS name,
       a.account_type   AS account_type,
       a.normal_balance AS normal_balance,
       COALESCE(agg.total_debit, 0)  AS total_debit,
       COALESCE(agg.total_credit, 0) AS total_credit
FROM accounting_account a
LEFT JOIN (
    SELECT l.account_id        AS account_id,
           SUM(l.debit)        AS total_debit,
           SUM(l.credit)       AS total_credit
    FROM accounting_journal_line l
    JOIN accounting_journal_entry e
      ON e.id = l.entry_id
     AND e.hub_id = l.hub_id
     AND e.is_deleted = 0
     AND e.status = 'posted'
    WHERE l.hub_id = :hub_id AND l.is_deleted = 0
      AND (:end_date = '' OR e.entry_date <= :end_date)
    GROUP BY l.account_id
) agg ON agg.account_id = a.id
WHERE a.hub_id = :hub_id AND a.is_deleted = 0 AND a.is_active = 1
ORDER BY a.code ASC;
