-- Un traslado por id (scope hub_id). Portado de MultiWarehouseService.get_transfer
-- (la cabecera; las líneas se piden por separado con multi_warehouse.transfers.lines).
SELECT id, transfer_number, source_warehouse_id, destination_warehouse_id, status,
       created_date, dispatched_date, received_date, carrier, tracking_ref, notes
FROM multi_warehouse_transfer
WHERE id = :transfer_id AND hub_id = :hub_id AND is_deleted = 0;
