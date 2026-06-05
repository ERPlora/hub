-- Reasignación de una actividad a otra referencia de usuario.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de ActivityService.reassign.
UPDATE activities_activity
SET assigned_to_ref = :new_assigned_to_ref,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :activity_id AND hub_id = :hub_id AND is_deleted = 0;
