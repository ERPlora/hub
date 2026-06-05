-- Plantillas de email del hub. Portado de TemplateService.list_templates.
-- El runtime inyecta :hub_id. Bind :active_only (0|1).
SELECT id, name, subject, variables, is_active, created_at, updated_at
FROM communications_email_template
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY name ASC;
