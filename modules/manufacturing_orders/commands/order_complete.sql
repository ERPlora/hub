-- Transición in_progress -> completed + cantidad producida + sello completed_at.
-- Portado de ManufacturingOrderService.complete_mo. Guard de estado en el WHERE
-- (solo 'in_progress'). La validación de quantity_produced >= 0 la hace el schema.
UPDATE manufacturing_orders_order
SET status = 'completed',
    quantity_produced = :quantity_produced,
    completed_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :mo_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'in_progress';
