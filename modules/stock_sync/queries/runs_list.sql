-- Runs de sincronización del hub, más recientes primero. Runtime inyecta :hub_id.
-- Portado de StockSyncService.list_runs / routes.list_runs. Filtros opcionales por estado y
-- canal origen (:status = '' / :source_id = '' = sin filtro). :limit acota el listado.
SELECT id, run_number, source_channel_id, target_channel_id, status,
       started_at, completed_at, items_synced, conflicts_count, error_log
FROM stock_sync_run
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status    = '' OR status            = :status)
  AND (:source_id = '' OR source_channel_id = :source_id)
ORDER BY started_at DESC
LIMIT :limit;
