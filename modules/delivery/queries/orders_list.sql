-- Pedidos de reparto/recogida del hub. Runtime inyecta :hub_id.
-- Portado de DeliveryService.list_orders. Filtros opcionales por status, order_type y
-- búsqueda libre sobre nombre/teléfono/número ('' = sin filtro). :limit acota el resultado.
SELECT id, number, order_type, customer_name, customer_phone, status,
       total, paid, ordered_at, delivery_zone_id, driver_id
FROM delivery_order
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:order_type = '' OR order_type = :order_type)
  AND (:search = ''
       OR customer_name  LIKE '%' || :search || '%'
       OR customer_phone LIKE '%' || :search || '%'
       OR number         LIKE '%' || :search || '%')
ORDER BY created_at DESC
LIMIT :limit;
