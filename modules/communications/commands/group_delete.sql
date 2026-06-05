-- Borrado lógico de grupo. Runtime inyecta :hub_id, :current_user_id, :now.
-- Los grupos del sistema (is_system=1) no deben borrarse: el guard va en el runtime/UI.
UPDATE communications_group
SET is_deleted = 1,
    deleted_at = :now,
    is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0 AND is_system = 0;
