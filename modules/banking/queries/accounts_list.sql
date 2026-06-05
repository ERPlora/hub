-- Cuentas bancarias del hub. Runtime inyecta :hub_id.
-- Portado de BankingService.list_accounts. :active_only ('1' = solo activas, '' = todas).
SELECT id, name, iban, bic, currency, opening_balance, current_balance, is_active, notes
FROM banking_account
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY name ASC;
