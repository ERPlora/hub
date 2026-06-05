-- Líneas (por producto) de un run de sincronización. Runtime inyecta :hub_id.
-- Portado de StockSyncRun.items. :run_id es obligatorio.
SELECT id, run_id, product_ref, source_quantity, target_quantity, action, resolved_at
FROM stock_sync_item
WHERE hub_id = :hub_id AND is_deleted = 0
  AND run_id = :run_id
ORDER BY product_ref ASC;
