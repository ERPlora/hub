-- Detalle completo de un pedido Uber Eats. Runtime inyecta :hub_id.
-- Portado de UberEatsService.get_order.
SELECT id, store_id, uber_order_id, order_number, customer_name, total_amount, currency,
       status, created_at_uber, items, customer_notes, created_at, updated_at
FROM uber_eats_order
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :id;
