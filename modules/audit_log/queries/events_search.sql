-- Búsqueda por subcadena en entity_repr, user_email_snapshot y el JSON serializado de
-- event_metadata. Portado de AuditService.search_events. Runtime inyecta :hub_id.
-- :q es el patrón ya envuelto en %…% por el SDK/runtime (LIKE case-insensitive).
-- La whitelist de campos (fields) del legacy se aplica en la UI/SDK; aquí buscamos en los tres.
SELECT id, event_type, entity_type, entity_id, entity_repr,
       user_ref, user_email_snapshot, user_role_snapshot,
       ip_address, severity, occurred_at
FROM audit_log_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (
        entity_repr        LIKE :q
     OR user_email_snapshot LIKE :q
     OR event_metadata     LIKE :q
  )
ORDER BY occurred_at DESC
LIMIT :limit;
