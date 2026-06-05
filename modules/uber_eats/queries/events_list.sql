-- Eventos de webhook recibidos de Uber, con filtros opcionales. Runtime inyecta :hub_id.
-- Apoya la auditoría/replay de la ingestión idempotente. Binds: :store_id, :status,
-- :event_type ('' = sin filtro en cada uno).
SELECT id, store_id, event_type, event_id, occurred_at, processed_at, status, payload, created_at
FROM uber_eats_event
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:store_id   = '' OR store_id   = :store_id)
  AND (:status     = '' OR status     = :status)
  AND (:event_type = '' OR event_type = :event_type)
ORDER BY created_at DESC;
