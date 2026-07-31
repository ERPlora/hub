INSERT INTO w140_items (id, hub_id, name, status, created_at, updated_at)
VALUES (:new_id, :hub_id, :name, 'pending', :now, :now);
