-- Registra una acción/tool del asistente (auditoría). Runtime inyecta :new_id,
-- :hub_id, :current_user_id, :now. Portado de los session.add(AssistantActionLog(...)).
-- tool_args/result son JSON serializado a TEXT. confirmed=0 => pendiente de confirmar.
INSERT INTO assistant_action_log
  (id, hub_id, conversation_id, tool_name, tool_args, result,
   success, confirmed, error_message, openai_call_id,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :conversation_id, :tool_name, :tool_args, :result,
   :success, :confirmed, :error_message, :openai_call_id,
   0, :current_user_id, :current_user_id, :now, :now);
