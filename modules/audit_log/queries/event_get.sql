-- Un evento de auditoría por id (scope hub_id). Portado de AuditService.get_event.
-- Devuelve también las columnas JSON de estado/cambios para la vista de detalle.
SELECT id, event_type, entity_type, entity_id, entity_repr,
       user_ref, user_email_snapshot, user_role_snapshot,
       ip_address, user_agent, before_state, after_state, changes,
       occurred_at, severity, event_metadata
FROM audit_log_event
WHERE id = :event_id AND hub_id = :hub_id AND is_deleted = 0;
