-- Alta de tarifa horaria. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de TimesheetService.create_hourly_rate. La validación rate > 0 la hace el
-- JSON Schema (minimum exclusivo). :employee_id puede venir vacío → guardar NULL lo
-- resuelve el runtime/SDK (string vacío → NULL).
INSERT INTO timesheets_hourly_rate
  (id, hub_id, name, rate, employee_id, is_default, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :rate, :employee_id, :is_default, 1,
   0, :current_user_id, :current_user_id, :now, :now);
