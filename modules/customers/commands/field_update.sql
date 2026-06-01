UPDATE customers_customerfield SET
  name = :name, field_type = :field_type, options = :options,
  is_required = :is_required, sort_order = :sort_order, is_active = :is_active,
  updated_by = :current_user_id, updated_at = :now
WHERE id = :field_id AND hub_id = :hub_id AND is_deleted = 0;
