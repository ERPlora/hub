-- Timeline de auditoría de un usuario concreto (más reciente primero), con rango opcional.
-- Portado de AuditService.get_user_activity. Runtime inyecta :hub_id.
-- :start_date/:end_date son ISO 8601 o '' (sin filtro).
SELECT id, event_type, entity_type, entity_id, entity_repr,
       user_ref, user_email_snapshot, user_role_snapshot,
       ip_address, severity, occurred_at
FROM audit_log_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND user_ref = :user_ref
  AND (:start_date = '' OR occurred_at >= :start_date)
  AND (:end_date   = '' OR occurred_at <= :end_date)
ORDER BY occurred_at DESC
LIMIT :limit;
