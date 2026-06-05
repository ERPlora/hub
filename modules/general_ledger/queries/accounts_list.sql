-- Cuentas del plan contable extendido. Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.list_accounts. Filtros opcionales por tipo y activo
-- ('' / -1 = sin filtro). Orden por código.
SELECT id, code, name, account_type, normal_balance, parent_id,
       is_summary, is_active, currency
FROM general_ledger_account
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:account_type = '' OR account_type = :account_type)
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
