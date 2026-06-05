-- Canales de sincronización del hub. Runtime inyecta :hub_id.
-- Portado de StockSyncService.list_channels. El filtro active_only lo aplica el bind
-- :active_only (1 = solo activos, 0 = todos).
SELECT id, code, name, channel_type, is_active, last_sync_at, settings, created_at
FROM stock_sync_channel
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
