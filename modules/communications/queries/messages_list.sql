-- Mensajes de un hilo, en orden cronológico. Portado de InboxService.get_thread (messages).
-- El runtime inyecta :hub_id.
SELECT id, thread_id, direction, message_type, sender_name, sender_address,
       recipient_addresses, cc_addresses, subject, body_text, body_html,
       status, created_at
FROM communications_message
WHERE hub_id = :hub_id AND is_deleted = 0 AND thread_id = :thread_id
ORDER BY created_at ASC;
