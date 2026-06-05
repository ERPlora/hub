-- Campañas del hub (filtro opcional por estado). Runtime inyecta :hub_id.
-- ('' = sin filtro). Las métricas (sent/delivered/failed) son contadores persistidos.
SELECT id, name, description, channel, template_id, status,
       scheduled_at, started_at, completed_at,
       total_recipients, sent_count, delivered_count, failed_count
FROM messaging_campaign
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
