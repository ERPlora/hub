-- Alta de conexión de marketplace. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de MarketplaceService.create_connection. La validación de platform contra el set
-- soportado (amazon/ebay/aliexpress/etsy/other) la hace el JSON Schema (enum).
-- La unicidad de code por hub la garantiza el índice ix_mp_connection_hub_code.
-- credentials/settings llegan como JSON serializado en el payload (default '{}').
INSERT INTO marketplaces_connection
  (id, hub_id, code, platform, name, is_active, credentials, region,
   last_sync_at, last_sync_status, settings,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :platform, :name, 1, :credentials, :region,
   NULL, '', '{}',
   0, :current_user_id, :current_user_id, :now, :now);
