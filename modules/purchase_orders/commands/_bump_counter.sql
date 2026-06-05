-- Incrementa atómicamente el contador de pedidos del día (upsert). Primera op de
-- create_order. Runtime inyecta :new_id, :hub_id. :day lo aporta el handler WASM.
-- Portado de models.generate_order_number (PO-YYYYMMDD-NNNN).
INSERT INTO purchase_orders_order_counter (id, hub_id, day, last_number)
VALUES (:new_id, :hub_id, :day, 1)
ON CONFLICT (hub_id, day) DO UPDATE SET last_number = last_number + 1;
