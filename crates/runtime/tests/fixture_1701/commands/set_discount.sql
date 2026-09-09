INSERT INTO p1701_order (id, hub_id, discount_percent, channel)
VALUES (:order_id, :hub_id, :discount_percent, :channel)
ON CONFLICT (id) DO UPDATE SET discount_percent = EXCLUDED.discount_percent
