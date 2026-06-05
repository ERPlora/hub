-- Transición de envío in_transit → delivered. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de CarriersService.mark_delivered. El guard de estado va EN la cláusula WHERE
-- (status='in_transit'): si no afecta filas, el runtime devuelve invalid_state.
UPDATE carriers_shipment
SET status = 'delivered',
    delivered_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :shipment_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'in_transit';
