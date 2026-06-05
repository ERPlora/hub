-- Edición de grupo. Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE communications_group
SET name        = :name,
    description = :description,
    icon        = :icon,
    color       = :color,
    is_active   = :is_active,
    is_default  = :is_default,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0;
