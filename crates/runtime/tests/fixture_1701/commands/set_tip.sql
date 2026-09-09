INSERT INTO p1701_order (id, hub_id, tip_percent)
VALUES (:order_id, :hub_id, :tip_percent)
ON CONFLICT (id) DO UPDATE SET tip_percent = EXCLUDED.tip_percent
