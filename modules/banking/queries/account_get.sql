-- Una cuenta bancaria por id (scope hub_id). Incluye el saldo cacheado current_balance.
-- Portado de la rama sin as_of_date de BankingService.get_account_balance.
SELECT id, name, iban, bic, currency, opening_balance, current_balance, is_active, notes
FROM banking_account
WHERE id = :account_id AND hub_id = :hub_id AND is_deleted = 0;
