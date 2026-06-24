SELECT id, name FROM catalog_items
WHERE hub_id = :hub_id AND is_deleted = 0
