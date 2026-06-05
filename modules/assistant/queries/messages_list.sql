-- Historial de mensajes de una conversación, en orden cronológico. Runtime inyecta
-- :hub_id. Portado de chat_page (filtro por conversation_id + order by created_at asc).
SELECT id, conversation_id, role, content, created_at
FROM assistant_message
WHERE hub_id = :hub_id AND is_deleted = 0
  AND conversation_id = :conversation_id
ORDER BY created_at ASC;
