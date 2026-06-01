INSERT INTO customers_customertag
  (id, hub_id, name, color, is_active, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :color, 1, 0, :current_user_id, :current_user_id, :now, :now);
