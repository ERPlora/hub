-- Alta de miembro del staff. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de StaffService.create_staff_member. role_id/hire_date pueden venir NULL.
INSERT INTO staff_member
  (id, hub_id, first_name, last_name, email, phone, employee_id,
   role_id, hire_date, status, bio, specialties, is_bookable,
   color, hourly_rate, commission_rate, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :first_name, :last_name, :email, :phone, :employee_id,
   :role_id, :hire_date, :status, :bio, :specialties, :is_bookable,
   :color, :hourly_rate, :commission_rate, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
