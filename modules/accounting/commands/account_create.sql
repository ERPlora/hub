-- Alta de cuenta en el plan contable. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de AccountingService.create_account. La validación de account_type, la inferencia de
-- normal_balance (debit-normal para asset/expense; credit-normal para liability/equity/income),
-- la comprobación de parent_id existente y el rechazo de code duplicado van a runtime/WASM
-- — ver WASM-TODO. El índice uq_account_hub_code garantiza la unicidad de (hub, code).
-- :parent_id puede ser '' → se persiste NULL. :normal_balance lo calcula el handler antes de insertar.
INSERT INTO accounting_account
  (id, hub_id, code, name, account_type, parent_id, is_active, normal_balance,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :account_type,
   NULLIF(:parent_id, ''), 1, :normal_balance,
   0, :current_user_id, :current_user_id, :now, :now);
