-- Detalle completo de un pedido Glovo. Runtime inyecta :hub_id.
-- Portado de GlovoService.get_order.
SELECT id, store_id, order_code, order_number, customer_name, customer_phone,
       total_amount, currency, status, created_at_glovo, items,
       delivery_address, notes, created_at
FROM glovo_order
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
