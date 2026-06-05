-- Pedidos Uber Eats con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de UberEatsService.list_orders. Binds: :store_id ('' = sin filtro),
-- :status ('' = sin filtro). El orden es por created_at descendente (más recientes primero).
SELECT id, store_id, uber_order_id, order_number, customer_name, total_amount, currency,
       status, created_at_uber, items, customer_notes, created_at
FROM uber_eats_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:store_id = '' OR store_id = :store_id)
  AND (:status   = '' OR status   = :status)
ORDER BY created_at DESC;
