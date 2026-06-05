-- Mensajes programados del hub, filtrables por estado. Portado de ScheduledService.list_scheduled.
-- El runtime inyecta :hub_id. Bind :status ('' = todos), por defecto la UI pasa 'pending'.
SELECT id, thread_id, account_id, recipient_addresses, cc_addresses,
       subject, scheduled_at, status, sent_at, error_message
FROM communications_scheduled_message
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY scheduled_at ASC;
