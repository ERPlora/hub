-- Quita una habilidad de un empleado (soft-delete). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de employee_skill_delete. No borra: marca is_deleted=1 y conserva histórico.
UPDATE training_employee_skill
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :employee_skill_id AND hub_id = :hub_id AND is_deleted = 0;
