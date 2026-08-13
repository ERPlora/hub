-- Writes its own table; the ON CONFLICT DO UPDATE clause must not read as "UPDATE set".
INSERT INTO scoped_ok_item (hub_id, id, n) VALUES (:hub_id, :new_id, 1)
ON CONFLICT (hub_id, id) DO UPDATE SET n = scoped_ok_item.n + 1;
