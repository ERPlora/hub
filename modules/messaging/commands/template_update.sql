-- Edición de plantilla. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de MessageTemplateUpdate. Solo plantillas del propio hub y no borradas.
UPDATE messaging_template
SET name       = :name,
    channel    = :channel,
    category   = :category,
    subject    = :subject,
    body       = :body,
    is_active  = :is_active,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
