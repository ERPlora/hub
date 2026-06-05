-- Cabecera de un pedido + datos del proveedor. Runtime inyecta :hub_id.
-- Portado de PurchaseOrderService.get_order (las líneas se piden con orders.lines).
SELECT
    o.id            AS id,
    o.order_number  AS order_number,
    o.status        AS status,
    o.supplier_id   AS supplier_id,
    s.name          AS supplier_name,
    s.email         AS supplier_email,
    s.phone         AS supplier_phone,
    o.order_date    AS order_date,
    o.expected_date AS expected_date,
    o.total_amount  AS total_amount,
    o.notes         AS notes,
    o.created_by    AS created_by
FROM purchase_orders_order o
LEFT JOIN purchase_orders_supplier s
       ON s.id = o.supplier_id AND s.hub_id = o.hub_id
WHERE o.id = :order_id
  AND o.hub_id = :hub_id
  AND o.is_deleted = 0;
