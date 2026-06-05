-- Mensajes enviados del hub (filtros opcionales por canal y estado). Runtime inyecta :hub_id.
-- Portado de MessageService.list_messages. ('' = sin filtro). :limit = nº máx. de filas.
SELECT id, channel, recipient_name, recipient_contact, subject, status,
       sent_at, delivered_at, read_at, external_id, created_at
FROM messaging_message
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:channel = '' OR channel = :channel)
  AND (:status  = '' OR status  = :status)
ORDER BY created_at DESC
LIMIT :limit;
