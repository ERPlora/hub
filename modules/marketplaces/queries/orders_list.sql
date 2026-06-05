-- Pedidos de marketplace del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de MarketplaceService.list_orders.
-- Binds opcionales: :connection_id ('' = todas), :status ('' = todos), :limit.
SELECT id, connection_id, external_order_id, order_number, customer_name,
       customer_email, total_amount, currency, order_date, status,
       shipping_address, items
FROM marketplaces_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
