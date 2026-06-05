-- Alta de conversación. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de _get_or_create_conversation (rama "create new").
INSERT INTO assistant_conversation
  (id, hub_id, openai_response_id, context,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, '', :context,
   0, :current_user_id, :current_user_id, :now, :now);
