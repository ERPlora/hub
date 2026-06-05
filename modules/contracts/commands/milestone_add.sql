-- Alta de hito de facturación. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ContractService.add_milestone. La validación de que el contrato existe
-- (en el mismo hub) y de que description no esté vacío la hace el runtime/schema.
INSERT INTO contracts_milestone
  (id, hub_id, contract_id, description, due_date, amount,
   is_invoiced, invoiced_at, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :contract_id, :description, :due_date, :amount,
   0, NULL, 0, :current_user_id, :current_user_id, :now, :now);
