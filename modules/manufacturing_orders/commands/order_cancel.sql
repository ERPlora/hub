-- Cancelación de una orden (cualquier estado salvo completed/cancelled).
-- Portado de ManufacturingOrderService.cancel_mo. Guard de estado en el WHERE.
-- NOTA: aquí NO se conserva el rastro textual de 'reason' en notes (eso requiere
-- componer notes con timestamp/append) -> ver WASM-TODO. Esta versión Tier 0 solo
-- marca el estado.
UPDATE manufacturing_orders_order
SET status = 'cancelled',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :mo_id AND hub_id = :hub_id AND is_deleted = 0
  AND status NOT IN ('completed', 'cancelled');
