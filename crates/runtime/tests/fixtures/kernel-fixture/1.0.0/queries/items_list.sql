SELECT id, name, created_by, created_at
FROM kfx_item
WHERE hub_id = :hub_id AND deleted_at IS NULL
