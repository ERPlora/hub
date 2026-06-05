-- Asignaciones (reparto a facturas) de un cobro. Runtime inyecta :hub_id.
-- Portado de CollectionService.get_collection (sub-consulta de allocations).
SELECT id, collection_id, invoice_ref, amount_allocated, allocated_at
FROM collections_allocation
WHERE hub_id = :hub_id AND collection_id = :collection_id AND is_deleted = 0
ORDER BY allocated_at ASC;
