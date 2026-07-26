SELECT id, name, hub_id FROM menu_items
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY name
