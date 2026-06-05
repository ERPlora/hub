-- Líneas de un traslado (scope hub_id). Portado de MultiWarehouseService.get_transfer
-- (la parte de líneas).
SELECT id, transfer_id, product_ref, quantity_requested, quantity_dispatched,
       quantity_received, lot_ref
FROM multi_warehouse_transfer_line
WHERE transfer_id = :transfer_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
