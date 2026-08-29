UPDATE kfx_item
SET deleted_at = :now, updated_at = :now
WHERE hub_id = :hub_id AND id = :id AND deleted_at IS NULL;
