-- Líneas activas de un pedido. Runtime inyecta :hub_id.
-- line_total (quantity * unit_price) lo calcula el SDK/UI a partir de estas columnas.
SELECT id, order_id, product_name, quantity, unit_price, notes
FROM delivery_order_item
WHERE order_id = :order_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
