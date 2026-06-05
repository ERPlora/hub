-- Alta de plantilla de turno. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ShiftTemplateMutationService.create_shift_template.
-- La validación HH:MM y end_time != start_time va en el schema/runtime; required_skills
-- llega como JSON string ('[]' por defecto).
INSERT INTO workforce_planning_shift_template
  (id, hub_id, name, location_id, start_time, end_time, break_minutes,
   color, is_active, min_staff, max_staff, role_required, required_skills,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :location_id, :start_time, :end_time, :break_minutes,
   :color, 1, :min_staff, :max_staff, :role_required, :required_skills,
   0, :current_user_id, :current_user_id, :now, :now);
