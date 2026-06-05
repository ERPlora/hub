-- Lista de pedidos de compra del hub con filtros opcionales (estado / proveedor).
-- Runtime inyecta :hub_id. Portado de PurchaseOrderService.list_orders.
-- :status y :supplier_id pueden venir vacíos ('') para no filtrar.
SELECT
    o.id            AS id,
    o.order_number  AS order_number,
    o.status        AS status,
    o.supplier_id   AS supplier_id,
    s.name          AS supplier_name,
    o.total_amount  AS total_amount,
    o.order_date    AS order_date,
    o.expected_date AS expected_date,
    o.created_at    AS created_at
FROM purchase_orders_order o
LEFT JOIN purchase_orders_supplier s
       ON s.id = o.supplier_id AND s.hub_id = o.hub_id
WHERE o.hub_id = :hub_id
  AND o.is_deleted = 0
  AND (:status = '' OR o.status = :status)
  AND (:supplier_id = '' OR o.supplier_id = :supplier_id)
ORDER BY o.created_at DESC
LIMIT :limit;
