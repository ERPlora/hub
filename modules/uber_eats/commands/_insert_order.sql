-- Inserción interna de un pedido, invocada por el handler WASM import_order tras resolver
-- idempotencia + generar el order_number. El handler aporta :new_id, :store_id, :uber_order_id,
-- :order_number, :customer_name, :total_amount, :currency, :created_at_uber, :items, :customer_notes.
-- Runtime inyecta :hub_id, :current_user_id, :now. status arranca en 'created'.
INSERT INTO uber_eats_order
  (id, hub_id, store_id, uber_order_id, order_number, customer_name, total_amount, currency,
   status, created_at_uber, items, customer_notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :store_id, :uber_order_id, :order_number, :customer_name, :total_amount, :currency,
   'created', :created_at_uber, :items, :customer_notes,
   0, :current_user_id, :current_user_id, :now, :now);
