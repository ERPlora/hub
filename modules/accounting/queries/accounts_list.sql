-- Plan de cuentas del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de AccountingService.list_accounts. Filtros opcionales por tipo y solo-activas.
-- (Los binds :account_type y :active_only deben pasarse: account_type '' = sin filtro;
--  active_only 1 = solo activas, 0 = todas.)
SELECT id, code, name, account_type, parent_id, is_active, normal_balance
FROM accounting_account
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:account_type = '' OR account_type = :account_type)
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
