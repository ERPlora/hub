-- Cambia el estado operativo (online|offline|closed) de una tienda Glovo y sella last_sync_at.
-- Portado de GlovoService.update_store_status. La validación del enum new_status la hace el
-- JSON Schema; el runtime revalida permiso y tenant.
UPDATE glovo_store
SET glovo_status = :new_status,
    last_sync_at = :now,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :store_id_internal AND hub_id = :hub_id AND is_deleted = 0;
