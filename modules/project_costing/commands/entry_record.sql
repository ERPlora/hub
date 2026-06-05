-- Registro de coste imputado a un proyecto, en estado 'pending'. Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now.
-- Portado de ProjectCostingService.record_cost. La validación de project_ref, cost_type
-- (enum), importe >= 0, fecha y horas la hace el JSON Schema. Si entry_date llega vacío,
-- el SDK/UI lo resuelve a la fecha de hoy antes de enviar.
INSERT INTO project_costing_entry
  (id, hub_id, project_ref, entry_date, cost_type, description, amount, hours,
   employee_ref, supplier_ref, status, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :project_ref, :entry_date, :cost_type, :description, :amount, :hours,
   :employee_ref, :supplier_ref, 'pending', :notes,
   0, :current_user_id, :current_user_id, :now, :now);
