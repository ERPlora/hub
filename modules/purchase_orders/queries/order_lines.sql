-- Líneas de un pedido de compra. Runtime inyecta :hub_id.
-- Portado de PurchaseOrderService.get_order (sublista de líneas).
SELECT
    id           AS id,
    product_name AS product_name,
    quantity     AS quantity,
    unit_price   AS unit_price,
    line_total   AS line_total
FROM purchase_orders_order_line
WHERE purchase_order_id = :order_id
  AND hub_id = :hub_id
  AND is_deleted = 0
ORDER BY created_at ASC;
