-- Detalle de un hilo concreto. Portado de InboxService.get_thread (cabecera).
-- Los mensajes del hilo se obtienen con communications.messages.list. El runtime inyecta :hub_id.
SELECT id, account_id, channel, contact_identifier, contact_name, customer_id,
       subject, status, priority, folder, assigned_to_id, group_id,
       unread_count, message_count, labels, last_message_at, snoozed_until
FROM communications_thread
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :thread_id
LIMIT 1;
