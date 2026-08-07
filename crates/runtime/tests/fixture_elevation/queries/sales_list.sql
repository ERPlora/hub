SELECT id, label, created_by, approved_by FROM till_sales
WHERE hub_id = :hub_id ORDER BY created_at ASC;
