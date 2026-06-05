-- Crea un SyncRun en estado 'running'. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de MarketplaceService.start_sync.
-- La validación de sync_type (products/orders/inventory/prices) la hace el JSON Schema (enum).
-- :now se usa también como started_at.
INSERT INTO marketplaces_sync_run
  (id, hub_id, connection_id, sync_type, started_at, completed_at, status,
   items_synced, items_failed, error_log,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :connection_id, :sync_type, :now, NULL, 'running',
   0, 0, '',
   0, :current_user_id, :current_user_id, :now, :now);
