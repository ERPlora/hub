-- Inserta una línea de comanda. Helper invocado por el handler WASM (create_order /
-- create_order_from_sale). Runtime inyecta :hub_id, :current_user_id, :now.
-- :new_id, :order_id, snapshot de producto y :total los aporta el handler.
INSERT INTO kitchen_orders_order_item
  (id, hub_id, order_id, station_id, product_id, product_name,
   unit_price, quantity, total, modifiers, notes, status, seat_number,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :order_id, :station_id, :product_id, :product_name,
   :unit_price, :quantity, :total, :modifiers, :notes, :status, :seat_number,
   0, :current_user_id, :current_user_id, :now, :now);
