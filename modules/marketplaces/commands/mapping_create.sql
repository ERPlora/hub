-- Alta de mapeo producto local ↔ listing externo. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de MarketplaceService.map_product.
-- La existencia de la conexión (FK) la valida el runtime; cross-módulo: local_product_ref
-- es una referencia opaca al catálogo (otro módulo lo OWNea, no se toca su tabla).
INSERT INTO marketplaces_product_mapping
  (id, hub_id, connection_id, local_product_ref, external_product_id, external_sku,
   sync_enabled, last_synced_at, sync_status, error_message,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :connection_id, :local_product_ref, :external_product_id, :external_sku,
   1, NULL, 'pending', '',
   0, :current_user_id, :current_user_id, :now, :now);
