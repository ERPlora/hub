-- Mapeos producto local ↔ listing externo (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de MarketplaceService.list_product_mappings.
-- Binds opcionales: :connection_id ('' = todas), :sync_status ('' = todos), :limit.
SELECT id, connection_id, local_product_ref, external_product_id, external_sku,
       sync_enabled, last_synced_at, sync_status, error_message
FROM marketplaces_product_mapping
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:sync_status = '' OR sync_status = :sync_status)
ORDER BY created_at DESC
LIMIT :limit;
