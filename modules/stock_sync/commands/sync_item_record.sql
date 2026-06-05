-- Añade una línea (por producto) a un run en curso. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de StockSyncService.record_sync_item.
-- La guarda de estado (el run debe estar 'running') y la validación de action (enum) se
-- documentan en WASM-TODO; el JSON Schema garantiza el enum de action a nivel de payload.
INSERT INTO stock_sync_item
  (id, hub_id, run_id, product_ref, source_quantity, target_quantity, action,
   resolved_at, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :run_id, :product_ref, :source_quantity, :target_quantity, :action,
   NULL, 0, :current_user_id, :current_user_id, :now, :now);
