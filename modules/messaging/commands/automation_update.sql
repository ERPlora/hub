-- Edición de automatización. Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE messaging_automation
SET name        = :name,
    description = :description,
    channel     = :channel,
    template_id = :template_id,
    delay_hours = :delay_hours,
    is_active   = :is_active,
    conditions  = :conditions,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
