-- Alta de tipo de ausencia. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de LeaveTypeService.create_leave_type. Validación de name no vacío en el schema.
INSERT INTO leave_type
  (id, hub_id, name, days_per_year, is_paid, color, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :days_per_year, :is_paid, :color, 1,
   0, :current_user_id, :current_user_id, :now, :now);
