-- Marca un número de serie vendido como devuelto. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de LotService.mark_serial_returned. El guard de estado (solo sold → returned) va en el WHERE.
UPDATE lots_serials_serial
SET status = 'returned',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :serial_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'sold';
