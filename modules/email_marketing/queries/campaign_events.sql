-- Eventos de tracking de una campaña (scope hub_id). Filtro opcional por event_type.
-- (:event_type = '' → todos). Base para get_campaign_metrics, que agrega en runtime/WASM.
SELECT id, campaign_id, subscriber_id, event_type, occurred_at, event_metadata
FROM email_marketing_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND campaign_id = :campaign_id
  AND (:event_type = '' OR event_type = :event_type)
ORDER BY occurred_at DESC;
