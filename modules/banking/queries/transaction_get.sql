-- Un apunte bancario por id (scope hub_id). Portado de BankingService.get_transaction.
SELECT id, account_id, transaction_date, value_date, amount, description,
       counterparty, reference, is_reconciled, reconciled_at, source
FROM banking_transaction
WHERE id = :transaction_id AND hub_id = :hub_id AND is_deleted = 0;
