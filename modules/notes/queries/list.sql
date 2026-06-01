SELECT id, title, body, created_at FROM notes
WHERE hub_id = :hub_id AND is_deleted = 0 ORDER BY created_at DESC;
