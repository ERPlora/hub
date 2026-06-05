-- Conversaciones del usuario activo, más recientes primero. Runtime inyecta :hub_id
-- y :current_user_id. Portado de history_page (filtro por created_by + context).
-- :context vacío = todos los contextos.
SELECT id, openai_response_id, context, created_at, updated_at
FROM assistant_conversation
WHERE hub_id = :hub_id AND is_deleted = 0
  AND created_by = :current_user_id
  AND (:context = '' OR context = :context)
ORDER BY updated_at DESC
LIMIT 50;
