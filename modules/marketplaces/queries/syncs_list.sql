-- Ejecuciones de sync recientes del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de routes.list_syncs / MarketplaceService.get_connection_summary (last_run).
-- Binds opcionales: :connection_id ('' = todas), :status ('' = todos), :sync_type ('' = todos), :limit.
SELECT id, connection_id, sync_type, started_at, completed_at, status,
       items_synced, items_failed, error_log
FROM marketplaces_sync_run
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:status = '' OR status = :status)
  AND (:sync_type = '' OR sync_type = :sync_type)
ORDER BY started_at DESC
LIMIT :limit;
