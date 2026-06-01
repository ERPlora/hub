UPDATE customers_customertag SET
  name = :name, color = :color, is_active = :is_active,
  updated_by = :current_user_id, updated_at = :now
WHERE id = :tag_id AND hub_id = :hub_id AND is_deleted = 0;
