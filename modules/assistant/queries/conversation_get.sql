-- Obtiene una conversación concreta del usuario activo. Runtime inyecta :hub_id y
-- :current_user_id. Portado de _get_or_create_conversation (reuse por id + dueño).
SELECT id, openai_response_id, context, created_at, updated_at
FROM assistant_conversation
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :conversation_id
  AND created_by = :current_user_id;
