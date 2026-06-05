-- Cabecera de un pedido por id (scope hub_id). Portado de OrderService.get.
-- Lee la tabla PROPIA orders_order (§2.3: nunca sales_sale).
-- La bitácora (orders_note) se carga aparte (orders.notes.list). Las líneas de la
-- venta vinculada, si existe sale_id, se piden por contrato sales.* (no SELECT directo).
SELECT id, order_number, status, channel, priority,
       customer_id, customer_name, customer_phone, delivery_address,
       requested_date, requested_time, total, notes, internal_notes,
       sale_id, created_at, updated_at
FROM orders_order
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
