-- Alta de requisito de cobertura. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CoverageRequirementCreate. day_of_week NULL = cualquier día.
INSERT INTO workforce_planning_coverage_requirement
  (id, hub_id, location_id, day_of_week, shift_template_id,
   min_employees, role_required, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :location_id, :day_of_week, :shift_template_id,
   :min_employees, :role_required, 1,
   0, :current_user_id, :current_user_id, :now, :now);
