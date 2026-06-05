-- Alta de cuenta del plan extendido. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de GeneralLedgerService.create_account. La validación de account_type, la
-- inferencia de normal_balance (DEFAULT_NORMAL_BALANCE), la existencia del parent y el
-- rechazo de code duplicado van al runtime/SDK (el índice uq_gl_account_hub_code refuerza
-- la unicidad). :parent_id = '' debe mapearse a NULL antes del bind.
INSERT INTO general_ledger_account
  (id, hub_id, code, name, account_type, normal_balance, parent_id,
   is_summary, is_active, currency,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :account_type, :normal_balance, :parent_id,
   :is_summary, 1, :currency,
   0, :current_user_id, :current_user_id, :now, :now);
