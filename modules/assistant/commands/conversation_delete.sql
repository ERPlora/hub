-- Borrado lógico de una conversación del usuario activo (soft-delete). Runtime inyecta
-- :hub_id, :current_user_id, :now. Los mensajes/logs quedan huérfanos lógicamente
-- (no se borran en cascada en soft-delete; el render los filtra por conversación).
UPDATE assistant_conversation
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :conversation_id
  AND created_by = :current_user_id;
