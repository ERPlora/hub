INSERT INTO kfx_item (id, hub_id, name, created_by, created_at, updated_at)
VALUES (:new_id, :hub_id, :name, :current_user_id, :now, :now);
