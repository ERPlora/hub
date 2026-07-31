SELECT id, name, status, touched_at FROM w140_items
WHERE hub_id = :hub_id ORDER BY name ASC;
