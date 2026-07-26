INSERT INTO menu_items (id, hub_id, name, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES (:new_id, :hub_id, :name, 0, :current_user_id, :current_user_id, :now, :now);
