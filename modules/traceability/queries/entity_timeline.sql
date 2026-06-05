-- Línea de tiempo ordenada (más antiguo → más reciente) de los eventos de una entidad.
-- Portado de TraceabilityService.get_entity_timeline. Runtime inyecta :hub_id.
SELECT id, event_type, entity_type, entity_ref, quantity,
       source_ref, destination_ref, related_document_type, related_document_ref,
       occurred_at, recorded_by, notes, metadata, created_at
FROM traceability_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND entity_type = :entity_type
  AND entity_ref  = :entity_ref
ORDER BY occurred_at ASC;
