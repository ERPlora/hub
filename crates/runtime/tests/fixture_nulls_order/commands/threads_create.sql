INSERT INTO nullsorder_thread (id, hub_id, label, last_message_at) VALUES (:new_id, :hub_id, :label, CAST(:last_message_at AS TIMESTAMPTZ));
