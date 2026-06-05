-- Comandas activas/recientes del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de OrderService.list_orders. Los filtros vacíos ('') desactivan el criterio.
-- (Binds: :status, :order_type, :priority, :table_id — '' = sin filtro; :limit.)
SELECT id, order_number, status, order_type, priority,
       table_id, sale_id, customer_id, waiter_id,
       round_number, notes, subtotal, tax, discount, total,
       fired_at, ready_at, served_at, created_at
FROM kitchen_orders_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status     = '' OR status     = :status)
  AND (:order_type = '' OR order_type = :order_type)
  AND (:priority   = '' OR priority   = :priority)
  AND (:table_id   = '' OR table_id   = :table_id)
ORDER BY created_at DESC
LIMIT :limit;
