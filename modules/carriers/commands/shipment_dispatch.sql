-- Transición de envío created → in_transit. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de CarriersService.dispatch_shipment. El guard de estado va EN la cláusula WHERE
-- (status='created'): si no afecta filas, el runtime devuelve invalid_state.
UPDATE carriers_shipment
SET status = 'in_transit',
    dispatched_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :shipment_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'created';
