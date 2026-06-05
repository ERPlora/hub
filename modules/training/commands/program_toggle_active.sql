-- Activa/desactiva un programa (flip de is_active). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de program_toggle. is_active se pasa ya invertido por el caller.
UPDATE training_program
SET is_active  = :is_active,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :program_id AND hub_id = :hub_id AND is_deleted = 0;
