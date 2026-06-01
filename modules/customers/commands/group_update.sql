UPDATE customers_customergroup SET
  name = :name, description = :description, discount_percent = :discount_percent,
  color = :color, sort_order = :sort_order, is_active = :is_active,
  updated_by = :current_user_id, updated_at = :now
WHERE id = :group_id AND hub_id = :hub_id AND is_deleted = 0;
