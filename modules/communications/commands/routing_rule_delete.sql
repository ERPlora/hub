-- Borrado lógico de regla de enrutado. Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE communications_routing_rule
SET is_deleted = 1,
    deleted_at = :now,
    is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0;
