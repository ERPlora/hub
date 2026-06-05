-- Alta de centro de coste. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de GeneralLedgerService.create_cost_center. La existencia del parent y el rechazo
-- de code duplicado los cubre el runtime/SDK (índice uq_gl_cost_center_hub_code).
-- :parent_id = '' debe mapearse a NULL antes del bind.
INSERT INTO general_ledger_cost_center
  (id, hub_id, code, name, parent_id, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :parent_id, 1,
   0, :current_user_id, :current_user_id, :now, :now);
