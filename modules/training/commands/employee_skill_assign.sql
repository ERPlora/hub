-- Asigna una habilidad a un empleado. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de skill_assign. La unicidad (employee_id, skill_id) la garantiza el índice
-- uq_training_es_employee_skill. employee_id es un StaffMember.id (módulo staff).
INSERT INTO training_employee_skill
  (id, hub_id, employee_id, employee_name, skill_id, proficiency_level, acquired_date, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :employee_id, :employee_name, :skill_id, :proficiency_level, :acquired_date, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
