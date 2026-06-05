-- Cola de contingencia: registros pendientes de reintento. Runtime inyecta :hub_id.
-- Portado de VerifactuService.list_contingency_queue + routes.contingency_view.
-- Bind opcional :status ('' = pendientes/reintentando por defecto lo decide la UI).
SELECT id, record_id, priority, queued_at, attempts,
       last_attempt_at, last_error, next_attempt_at, status
FROM verifactu_contingencyqueue
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY priority ASC, queued_at ASC
LIMIT :limit;
