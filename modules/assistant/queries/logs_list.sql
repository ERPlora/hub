-- Log de acciones del usuario activo, más recientes primero. Runtime inyecta :hub_id
-- y :current_user_id. Portado de logs_page (filtro por created_by + order by created_at desc).
SELECT id, conversation_id, tool_name, tool_args, result,
       success, confirmed, error_message, created_at
FROM assistant_action_log
WHERE hub_id = :hub_id AND is_deleted = 0
  AND created_by = :current_user_id
ORDER BY created_at DESC
LIMIT 100;
