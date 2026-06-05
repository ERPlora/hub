-- Cabecera de una comanda concreta. Runtime inyecta :hub_id.
-- Portado de OrderService.get_order (las líneas se obtienen con order_items.sql).
SELECT id, order_number, status, order_type, priority,
       table_id, sale_id, customer_id, waiter_id,
       round_number, notes, subtotal, tax, discount, total,
       fired_at, ready_at, served_at, created_at
FROM kitchen_orders_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :order_id;
