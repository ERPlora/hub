-- Incrementa atómicamente el contador de ventas del día (upsert). Primera op de
-- complete_sale. Runtime inyecta :new_id, :hub_id. :day lo aporta el handler.
INSERT INTO sales_sale_counter (id, hub_id, day, last_number)
VALUES (:new_id, :hub_id, :day, 1)
ON CONFLICT (hub_id, day) DO UPDATE SET last_number = last_number + 1;
