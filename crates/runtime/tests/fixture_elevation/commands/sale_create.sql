INSERT INTO till_sales (id, hub_id, label, created_by, approved_by, created_at)
VALUES (:new_id, :hub_id, :label, :current_user_id, :approved_by, :now);
