-- Histórico de sincronizaciones de menú de una tienda. Runtime inyecta :hub_id.
-- Bind :store_id obligatorio. Más recientes primero.
SELECT id, store_id, sync_type, started_at, completed_at, status,
       items_synced, error_log
FROM glovo_menu_sync
WHERE hub_id = :hub_id AND is_deleted = 0 AND store_id = :store_id
ORDER BY started_at DESC
LIMIT :limit;
