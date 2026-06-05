-- Lista de eventos de auditoría (más reciente primero) con filtros opcionales.
-- Runtime inyecta :hub_id. Portado de AuditService.list_events.
-- Binds opcionales: '' = sin filtro. Las fechas (:start_date/:end_date) son ISO 8601 o ''.
SELECT id, event_type, entity_type, entity_id, entity_repr,
       user_ref, user_email_snapshot, user_role_snapshot,
       ip_address, severity, occurred_at
FROM audit_log_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:event_type  = '' OR event_type  = :event_type)
  AND (:entity_type = '' OR entity_type = :entity_type)
  AND (:user_ref    = '' OR user_ref    = :user_ref)
  AND (:severity    = '' OR severity    = :severity)
  AND (:start_date  = '' OR occurred_at >= :start_date)
  AND (:end_date    = '' OR occurred_at <= :end_date)
ORDER BY occurred_at DESC
LIMIT :limit;
