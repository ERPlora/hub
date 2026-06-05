-- Log de auditoría / eventos VeriFactu (más recientes primero). Runtime inyecta :hub_id.
-- Portado de routes.events_list. Binds opcionales: :event_type y :severity ('' = sin filtro).
SELECT id, record_id, event_type, severity, message, details, timestamp
FROM verifactu_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:event_type = '' OR event_type = :event_type)
  AND (:severity = '' OR severity = :severity)
ORDER BY timestamp DESC
LIMIT :limit;
