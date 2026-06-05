-- Inserta la cabecera del pedido (paso interno de create_order, llamado por el handler WASM).
-- El handler aporta :order_number (PO-YYYYMMDD-NNNN), :total_amount (suma de líneas) y :expected_date.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO purchase_orders_order
  (id, hub_id, supplier_id, order_number, status, order_date, expected_date,
   total_amount, notes, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :supplier_id, :order_number, 'draft', :now, :expected_date,
   :total_amount, :notes, 0, :current_user_id, :current_user_id, :now, :now);
