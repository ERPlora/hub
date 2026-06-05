-- Campañas del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de EmailMarketingService.list_campaigns. Filtros: :status='' y :list_id='' = sin filtro.
SELECT id, name, subject, sender_name, sender_email, list_id, status,
       scheduled_for, sent_at, total_sent, total_opens, total_clicks,
       total_bounces, created_at
FROM email_marketing_campaign
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status  = '' OR status  = :status)
  AND (:list_id = '' OR list_id = :list_id)
ORDER BY created_at DESC
LIMIT :limit;
