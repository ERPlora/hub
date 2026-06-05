-- Apuntes bancarios del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de BankingService.list_transactions. Binds opcionales ('' / -1 = sin filtro):
--   :account_id  (uuid de cuenta o '')
--   :start_date  (ISO YYYY-MM-DD o '')      transaction_date >=
--   :end_date    (ISO YYYY-MM-DD o '')      transaction_date <=
--   :reconciled  ('1' | '0' | '' sin filtro)
--   :limit       (entero; tope de filas)
SELECT id, account_id, transaction_date, value_date, amount, description,
       counterparty, reference, is_reconciled, reconciled_at, source
FROM banking_transaction
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:account_id = '' OR account_id = :account_id)
  AND (:start_date = '' OR transaction_date >= :start_date)
  AND (:end_date   = '' OR transaction_date <= :end_date)
  AND (:reconciled = '' OR is_reconciled = CAST(:reconciled AS INTEGER))
ORDER BY transaction_date DESC
LIMIT :limit;
