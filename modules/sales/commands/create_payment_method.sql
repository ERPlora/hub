INSERT INTO sales_payment_method
  (id, hub_id, name, type, icon, is_active, sort_order, opens_cash_drawer, requires_change,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :type, :icon, 1, :sort_order, :opens_cash_drawer, :requires_change,
   0, :current_user_id, :current_user_id, :now, :now);
