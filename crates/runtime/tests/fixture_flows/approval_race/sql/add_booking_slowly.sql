INSERT INTO race_booking (id, hub_id, created_by, text) SELECT :new_id, :hub_id, :current_user_id, COALESCE(:text, '') FROM (SELECT pg_sleep(0.8)) AS slow;
