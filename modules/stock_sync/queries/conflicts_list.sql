-- Conflictos del hub (por defecto la cola 'open'), más recientes primero. Runtime inyecta :hub_id.
-- Portado de StockSyncService.list_conflicts / routes.list_conflicts. Filtros opcionales por
-- estado y canal origen (:status = '' / :channel_id = '' = sin filtro). :limit acota el listado.
SELECT id, product_ref, source_channel_id, target_channel_id,
       source_quantity, target_quantity, detected_at, status,
       resolution_strategy, resolved_at
FROM stock_sync_conflict
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status     = '' OR status            = :status)
  AND (:channel_id = '' OR source_channel_id = :channel_id)
ORDER BY detected_at DESC
LIMIT :limit;
