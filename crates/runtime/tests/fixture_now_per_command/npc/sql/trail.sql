INSERT INTO npc_trail (hub_id, item_id, stamped_at, handler_now, payload_now)
SELECT i.hub_id, i.id, :now, :handler_now, :payload_now
FROM npc_item i
WHERE i.hub_id = :hub_id AND i.id = :id AND i.updated_at = :now;
