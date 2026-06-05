-- Alta de cuenta bancaria. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de BankingService.create_account. current_balance arranca == opening_balance
-- (el payload trae el mismo valor en :opening_balance para ambas columnas); luego lo
-- mantienen los apuntes (banking.transactions.add → WASM). (hub_id, iban) único por índice.
INSERT INTO banking_account
  (id, hub_id, name, iban, bic, currency, opening_balance, current_balance,
   is_active, notes, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :iban, :bic, :currency, :opening_balance, :opening_balance,
   1, :notes, 0, :current_user_id, :current_user_id, :now, :now);
