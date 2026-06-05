-- Plantillas del hub (filtros opcionales por canal y activo). Runtime inyecta :hub_id.
-- Portado de TemplateService.list_templates. ('' / -1 = sin filtro).
SELECT id, name, channel, category, subject, body, is_active, is_system
FROM messaging_template
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:channel = '' OR channel = :channel)
  AND (:is_active = -1 OR is_active = :is_active)
ORDER BY name ASC;
