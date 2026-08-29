-- Regression fixture for ERPlora/hub#978: a command that spends 400 ms INSIDE the database, so two
-- of them in flight can only finish in ~400 ms total if the server lets them overlap.
INSERT INTO slowtill_sales (id, hub_id, label, created_by, created_at)
SELECT :new_id, :hub_id, :label, :current_user_id, :now FROM pg_sleep(0.4);
