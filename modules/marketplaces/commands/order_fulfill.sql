-- Transición de un pedido a 'fulfilled'. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de MarketplaceService.mark_order_fulfilled. La guarda de estado (solo desde
-- 'imported'/'new', NO desde 'cancelled' ni 'fulfilled') se expresa aquí en el WHERE: si el
-- pedido ya está fulfilled o cancelled, no se actualiza ninguna fila y el runtime devuelve
-- el error de estado inválido. Las reglas detalladas de transición están en WASM-TODO.
UPDATE marketplaces_order
SET status = 'fulfilled',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :order_id AND hub_id = :hub_id AND is_deleted = 0
  AND status NOT IN ('fulfilled', 'cancelled');
