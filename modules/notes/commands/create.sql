INSERT INTO notes (id, hub_id, title, body, is_deleted, created_by, created_at)
VALUES (:new_id, :hub_id, :title, :body, 0, :current_user_id, :now);
