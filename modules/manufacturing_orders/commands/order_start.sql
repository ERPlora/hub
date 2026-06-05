-- Transición released -> in_progress + sello started_at. Portado de
-- ManufacturingOrderService.start_mo. Guard de estado en el WHERE (solo 'released').
UPDATE manufacturing_orders_order
SET status = 'in_progress',
    started_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :mo_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'released';
