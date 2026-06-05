-- Pipeline de pedidos: filas de la tabla PROPIA del módulo orders (orders_order).
-- Portado de OrderService.list (filtros opcionales status/channel/search, orden por fecha desc).
-- Cross-module §2.3: orders NO lee sales_sale; lee SU tabla. Si hace falta dato de la venta
-- vinculada, se resuelve por sale_id vía contrato sales.* (no SELECT directo).
-- Runtime inyecta :hub_id. Los binds de filtro se pasan vacíos ('') para no filtrar.
SELECT id, order_number, status, channel, customer_name, customer_phone,
       total, priority, sale_id, created_at
FROM orders_order
WHERE hub_id = :hub_id
  AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:channel = '' OR channel = :channel)
  AND (:search = '' OR order_number LIKE '%' || :search || '%'
                    OR customer_name LIKE '%' || :search || '%'
                    OR customer_phone LIKE '%' || :search || '%')
ORDER BY created_at DESC
LIMIT 50;
