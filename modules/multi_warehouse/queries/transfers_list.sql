-- Traslados del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de MultiWarehouseService.list_transfers. Binds opcionales: '' = sin filtro.
-- Orden: más recientes primero (created_at desc).
SELECT id, transfer_number, source_warehouse_id, destination_warehouse_id, status,
       created_date, dispatched_date, received_date, carrier, tracking_ref, notes
FROM multi_warehouse_transfer
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status         = '' OR status                   = :status)
  AND (:source_id      = '' OR source_warehouse_id      = :source_id)
  AND (:destination_id = '' OR destination_warehouse_id = :destination_id)
ORDER BY created_at DESC;
