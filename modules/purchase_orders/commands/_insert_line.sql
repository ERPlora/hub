-- Inserta una línea del pedido (paso interno de create_order, llamado por el handler WASM
-- una vez por línea). El handler aporta :line_total = quantity * unit_price (calculado fuera de SQL).
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO purchase_orders_order_line
  (id, hub_id, purchase_order_id, product_name, quantity, unit_price, line_total,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :purchase_order_id, :product_name, :quantity, :unit_price, :line_total,
   0, :current_user_id, :current_user_id, :now, :now);
