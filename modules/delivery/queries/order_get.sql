-- Detalle de cabecera de un pedido. Runtime inyecta :hub_id.
-- Portado de DeliveryService.get_order (las líneas se obtienen con delivery.orders.items).
SELECT id, number, order_type, customer_name, customer_phone, delivery_address,
       delivery_zone_id, driver_id, sale_id, status, ordered_at, promised_at,
       completed_at, subtotal, delivery_fee, total, payment_method, paid, notes
FROM delivery_order
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
