-- Actualización interna de un menú existente, invocada por el handler WASM sync_menu cuando
-- el uber_menu_id ya existe (rama upsert). El handler aporta :id, :name, :items_count.
-- Runtime inyecta :hub_id, :current_user_id, :now. Refresca last_synced_at y sync_status.
UPDATE uber_eats_menu
SET name           = :name,
    items_count    = :items_count,
    last_synced_at = :now,
    sync_status    = 'synced',
    updated_by     = :current_user_id,
    updated_at     = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
