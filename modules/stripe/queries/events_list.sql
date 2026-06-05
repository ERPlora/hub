-- Eventos de webhook del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de StripeService.list_webhook_events. (:connection_id/:status/:event_type = '' → sin filtro.)
SELECT id, connection_id, event_id, event_type, occurred_at, processed_at,
       status, error_message, created_at
FROM stripe_webhook_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:status        = '' OR status        = :status)
  AND (:event_type    = '' OR event_type    = :event_type)
ORDER BY created_at DESC
LIMIT :limit;
