-- Borrado lógico (soft-delete) de un centro de trabajo. NO borra físicamente:
-- preserva el histórico de fichajes que lo referencian. Runtime inyecta :current_user_id, :now.
UPDATE time_control_workplace
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :workplace_id AND hub_id = :hub_id AND is_deleted = 0;
