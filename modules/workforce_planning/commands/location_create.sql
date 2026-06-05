-- Alta de sede. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de LocationMutationService.create_location.
INSERT INTO workforce_planning_location
  (id, hub_id, name, address, phone, email, manager_employee_id,
   timezone, is_active, color, sort_order,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :address, :phone, :email, :manager_employee_id,
   :timezone, 1, :color, :sort_order,
   0, :current_user_id, :current_user_id, :now, :now);
