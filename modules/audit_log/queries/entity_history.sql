-- Timeline de auditoría de una entidad concreta (más reciente primero).
-- Portado de AuditService.get_entity_history. Runtime inyecta :hub_id.
SELECT id, event_type, entity_type, entity_id, entity_repr,
       user_ref, user_email_snapshot, user_role_snapshot,
       ip_address, severity, occurred_at
FROM audit_log_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND entity_type = :entity_type
  AND entity_id   = :entity_id
ORDER BY occurred_at DESC
LIMIT :limit;
