-- Alta de canal de sincronización. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de StockSyncService.create_channel. La validación de channel_type (enum) y la
-- unicidad de code la garantiza el JSON Schema + el índice ix_stock_sync_channel_hub_code.
INSERT INTO stock_sync_channel
  (id, hub_id, code, name, channel_type, is_active, last_sync_at, settings,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :channel_type, 1, NULL, :settings,
   0, :current_user_id, :current_user_id, :now, :now);
