-- Bitácora (últimas 10 entradas) de un pedido. Portado de OrderService.get (notes).
-- Referencia el pedido por order_id (tabla propia orders_order). Runtime inyecta :hub_id.
SELECT id, note_type, content, author_name, from_status, to_status, created_at
FROM orders_note
WHERE hub_id = :hub_id AND is_deleted = 0 AND order_id = :order_id
ORDER BY created_at DESC
LIMIT 10;
