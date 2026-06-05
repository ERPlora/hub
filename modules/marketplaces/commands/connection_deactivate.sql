-- Desactivación de una conexión (NO borra: la saca de selecciones por defecto).
-- Portado de MarketplaceService.deactivate_connection. La guarda "ya inactiva" (already_inactive)
-- la resuelve el runtime/UI; aquí el UPDATE es idempotente sobre filas activas.
UPDATE marketplaces_connection
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :connection_id AND hub_id = :hub_id AND is_deleted = 0;
