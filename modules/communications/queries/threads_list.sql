-- Hilos del inbox del hub, filtrables por carpeta/estado/solo-no-leídos.
-- Portado de InboxService.list_inbox / search_emails. El runtime inyecta :hub_id.
-- Binds opcionales: ('' = sin filtro) :folder, :status; :unread_only (0|1).
SELECT id, account_id, channel, contact_identifier, contact_name,
       subject, status, priority, folder, assigned_to_id, group_id,
       unread_count, message_count, last_message_at
FROM communications_thread
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:folder = '' OR folder = :folder)
  AND (:status = '' OR status = :status)
  AND (:unread_only = 0 OR unread_count > 0)
ORDER BY last_message_at DESC, created_at DESC;
