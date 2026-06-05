-- Actualiza el nivel de competencia de un empleado en una habilidad.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de employee_skill_update.
UPDATE training_employee_skill
SET proficiency_level = :proficiency_level,
    acquired_date     = :acquired_date,
    notes             = :notes,
    updated_by        = :current_user_id,
    updated_at        = :now
WHERE id = :employee_skill_id AND hub_id = :hub_id AND is_deleted = 0;
