-- Anula una venta (no la borra). El bloqueo fiscal por factura activa se valida
-- en fase posterior con invoice. Portado de m_sales.void_sale.
UPDATE sales_sale
SET status = 'voided',
    notes = notes || char(10) || '[VOIDED] ' || :reason,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :sale_id AND hub_id = :hub_id AND status NOT IN ('voided', 'refunded', 'draft');
