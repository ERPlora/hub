-- Alta de un hito facturable en un contrato. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ProjectBillingService.add_milestone. La existencia del contrato (mismo hub) la valida
-- el runtime contra la query contract.get antes de ejecutar; aquí solo se inserta.
INSERT INTO project_billing_milestone
  (id, hub_id, contract_id, name, due_date, amount, status,
   invoiced_at, paid_at, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :contract_id, :name, :due_date, :amount, 'pending',
   NULL, NULL, 0, :current_user_id, :current_user_id, :now, :now);
