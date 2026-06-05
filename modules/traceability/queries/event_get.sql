-- Un evento de trazabilidad por id (scope hub_id). Portado de TraceabilityService.get_event.
SELECT id, event_type, entity_type, entity_ref, quantity,
       source_ref, destination_ref, related_document_type, related_document_ref,
       occurred_at, recorded_by, notes, metadata, created_at
FROM traceability_event
WHERE id = :event_id AND hub_id = :hub_id AND is_deleted = 0;
