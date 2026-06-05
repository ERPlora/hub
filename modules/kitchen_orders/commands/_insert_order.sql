-- Inserta la cabecera de comanda. Helper invocado por el handler WASM (create_order /
-- create_order_from_sale). Runtime inyecta :hub_id, :current_user_id, :now.
-- :new_id y los totales/order_number los aporta el handler.
INSERT INTO kitchen_orders_order
  (id, hub_id, order_number, table_id, sale_id, customer_id, waiter_id,
   order_type, status, priority, round_number, notes,
   subtotal, tax, discount, total,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :order_number, :table_id, :sale_id, :customer_id, :waiter_id,
   :order_type, :status, :priority, :round_number, :notes,
   :subtotal, :tax, :discount, :total,
   0, :current_user_id, :current_user_id, :now, :now);
