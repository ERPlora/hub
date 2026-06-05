-- Cambia el estado operativo de una tienda (active|paused|offline) y sella last_sync_at.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de UberEatsService.update_store_status.
-- La validación de que :new_status pertenece a {active,paused,offline} la hace el JSON Schema.
UPDATE uber_eats_store
SET status     = :new_status,
    last_sync_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
