INSERT INTO customers_customerfieldvalue
  (id, hub_id, customer_id, field_id, value, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES (:new_id, :hub_id, :customer_id, :field_id, :value, 0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT (customer_id, field_id) DO UPDATE SET value = :value, updated_by = :current_user_id, updated_at = :now;
