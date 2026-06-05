-- Detalle completo de una plantilla. Portado de TemplateService.get_template.
-- El runtime inyecta :hub_id.
SELECT id, name, subject, body_html, body_text, variables, is_active,
       created_at, updated_at
FROM communications_email_template
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :template_id
LIMIT 1;
