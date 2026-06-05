-- Lista de eventos de trazabilidad del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de TraceabilityService.list_events / routes.list_events.
-- Los binds opcionales deben pasarse: '' = sin filtro. El filtro por rango de fechas
-- (start_date/end_date sobre occurred_at) lo aplica el SDK/UI; aquí devolvemos lo no-borrado.
SELECT id, event_type, entity_type, entity_ref, quantity,
       source_ref, destination_ref, related_document_type, related_document_ref,
       occurred_at, recorded_by, notes, metadata, created_at
FROM traceability_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:entity_type = '' OR entity_type = :entity_type)
  AND (:entity_ref  = '' OR entity_ref  = :entity_ref)
  AND (:event_type  = '' OR event_type  = :event_type)
ORDER BY occurred_at DESC;
