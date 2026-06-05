-- Inserción interna de un menú, invocada por el handler WASM sync_menu cuando el
-- uber_menu_id no existe aún. El handler aporta :new_id, :store_id, :uber_menu_id, :name,
-- :items_count. Runtime inyecta :hub_id, :current_user_id, :now. sync_status='synced'.
INSERT INTO uber_eats_menu
  (id, hub_id, store_id, uber_menu_id, name, items_count, last_synced_at, sync_status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :store_id, :uber_menu_id, :name, :items_count, :now, 'synced',
   0, :current_user_id, :current_user_id, :now, :now);
