-- Asignaciones (números emitidos) de una serie, las más recientes primero.
-- Portado de InvoiceSeriesService.list_allocations (scope hub_id + series_id, limit configurable).
SELECT id, series_id, document_number, document_ref, created_at AS allocated_at
FROM invoice_series_allocation
WHERE hub_id = :hub_id AND series_id = :series_id AND is_deleted = 0
ORDER BY created_at DESC
LIMIT :limit;
