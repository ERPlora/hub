-- Automatizaciones del hub (filtro opcional por activo). Runtime inyecta :hub_id.
-- Portado de AutomationService.list_automations. (-1 = sin filtro).
SELECT id, name, description, trigger, channel, template_id,
       delay_hours, is_active, total_sent, last_triggered_at
FROM messaging_automation
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:is_active = -1 OR is_active = :is_active)
ORDER BY name ASC;
