-- Borrado lógico de automatización (soft-delete). Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE messaging_automation
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
