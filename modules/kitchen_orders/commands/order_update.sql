-- Actualización de campos editables de una comanda. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de OrderService.update_order. COALESCE deja sin tocar los campos no enviados.
UPDATE kitchen_orders_order
SET notes       = COALESCE(:notes, notes),
    priority    = COALESCE(:priority, priority),
    order_type  = COALESCE(:order_type, order_type),
    table_id    = COALESCE(:table_id, table_id),
    waiter_id   = COALESCE(:waiter_id, waiter_id),
    customer_id = COALESCE(:customer_id, customer_id),
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0;
