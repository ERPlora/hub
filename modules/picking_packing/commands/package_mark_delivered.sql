-- Transición shipped → delivered. Runtime inyecta :current_user_id, :now, :hub_id.
-- Portado de PickPackService.mark_delivered. La guarda de estado se expresa en el WHERE
-- (status='shipped'): si no está en shipped no se actualiza ninguna fila.
UPDATE picking_packing_package
SET status = 'delivered',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :package_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'shipped';
