UPDATE customers_customerfield
SET is_active = 0, is_deleted = 1, deleted_at = :now,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :field_id AND hub_id = :hub_id;
