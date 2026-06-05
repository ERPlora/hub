-- Alta de presupuesto de proyecto en estado 'draft'. Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now.
-- Portado de ProjectCostingService.create_budget. La validación de project_ref,
-- importe y año fiscal la hace el JSON Schema; currency se normaliza en mayúsculas
-- en el SDK/UI antes de enviar.
INSERT INTO project_costing_budget
  (id, hub_id, project_ref, budget_amount, currency, fiscal_year, status,
   approved_by_ref, approved_at, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :project_ref, :budget_amount, :currency, :fiscal_year, 'draft',
   '', NULL, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
