-- Borrado lógico de un workflow (soft-delete). Runtime inyecta :hub_id, :current_user_id, :now.
-- Sus runs/steps quedan en BD como histórico (cascada física solo si se borrara la fila real).
UPDATE workflows_workflow
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :workflow_id AND hub_id = :hub_id AND is_deleted = 0;
