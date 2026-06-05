-- Abre una sesión de sincronización de menú (estado 'running'). Runtime inyecta
-- :new_id, :hub_id, :current_user_id, :now. Portado de GlovoService.start_menu_sync.
-- El enum sync_type lo valida el JSON Schema; que la tienda exista lo revalida el runtime.
INSERT INTO glovo_menu_sync
  (id, hub_id, store_id, sync_type, started_at, completed_at, status,
   items_synced, error_log, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :store_id_internal, :sync_type, :now, NULL, 'running',
   0, '', 0, :current_user_id, :current_user_id, :now, :now);
