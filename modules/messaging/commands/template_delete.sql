-- Borrado lógico de plantilla (soft-delete). Runtime inyecta :hub_id, :current_user_id, :now.
-- No se borran plantillas de sistema (is_system = 1).
UPDATE messaging_template
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0 AND is_system = 0;
