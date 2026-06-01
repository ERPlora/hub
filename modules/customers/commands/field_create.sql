INSERT INTO customers_customerfield
  (id, hub_id, name, field_type, options, is_required, sort_order, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :field_type, :options, :is_required, :sort_order, 1,
   0, :current_user_id, :current_user_id, :now, :now);
