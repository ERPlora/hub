-- Edición de plantilla. Portado de TemplateService.update_template (full update).
-- Runtime inyecta :hub_id, :current_user_id, :now. :variables es JSON (TEXT).
UPDATE communications_email_template
SET name       = :name,
    subject    = :subject,
    body_html  = :body_html,
    body_text  = :body_text,
    variables  = :variables,
    is_active  = :is_active,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0;
