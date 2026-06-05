-- Pedidos Glovo del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de GlovoService.list_orders. Binds :store_id y :status: '' = sin filtro.
SELECT id, store_id, order_code, order_number, customer_name, customer_phone,
       total_amount, currency, status, created_at_glovo, items,
       delivery_address, notes, created_at
FROM glovo_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:store_id = '' OR store_id = :store_id)
  AND (:status   = '' OR status   = :status)
ORDER BY created_at DESC
LIMIT :limit;
