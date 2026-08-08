INSERT INTO till_drawer_event (id, hub_id, reason, created_by, created_at)
VALUES (:new_id, :hub_id, :reason, :current_user_id, :now);
