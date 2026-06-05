-- Transición draft -> released. Portado de ManufacturingOrderService.release_mo.
-- El guard de estado va en el WHERE (solo afecta filas en 'draft'); si no afecta
-- ninguna fila, el runtime lo trata como conflicto de estado (invalid_state).
UPDATE manufacturing_orders_order
SET status = 'released',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :mo_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
