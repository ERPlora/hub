-- Marca un número de serie como vendido. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de LotService.mark_serial_sold. El guard de estado (solo in_stock → sold) se expresa
-- en el WHERE: si el serial no está in_stock no se actualiza ninguna fila (runtime devuelve el error).
UPDATE lots_serials_serial
SET status = 'sold',
    sold_at = :now,
    sold_to_customer = :customer_name,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :serial_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'in_stock';
