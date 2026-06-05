-- Añade un mensaje al historial local. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de los session.add(AssistantMessage(...)) del
-- bucle de chat. La conversación debe existir y pertenecer al usuario (lo valida el
-- runtime/handler; ver WASM-TODO §persistencia). role = user|assistant|system.
INSERT INTO assistant_message
  (id, hub_id, conversation_id, role, content,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :conversation_id, :role, :content,
   0, :current_user_id, :current_user_id, :now, :now);
