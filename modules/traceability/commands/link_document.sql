-- Adjunta una referencia de documento de negocio a un evento existente.
-- Portado de TraceabilityService.link_to_document. Runtime inyecta :hub_id, :current_user_id, :now.
-- La guarda de existencia (evento no encontrado) la resuelve el runtime antes de ejecutar.
UPDATE traceability_event
SET related_document_type = :document_type,
    related_document_ref  = :document_ref,
    updated_by            = :current_user_id,
    updated_at            = :now
WHERE id = :event_id AND hub_id = :hub_id AND is_deleted = 0;
