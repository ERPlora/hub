INSERT INTO npc_item (hub_id, id, updated_at) VALUES (:hub_id, :id, :now)
ON CONFLICT (hub_id, id) DO UPDATE SET updated_at = :now;
