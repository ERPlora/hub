-- Registro de llamadas a la API (auditoría), más reciente primero. Runtime inyecta :hub_id.
-- Portado de CourierService.list_calls / routes.api_logs.
-- (:connection_id = '' → sin filtro; :status = '' → sin filtro; :call_type = '' → sin filtro.)
SELECT id, connection_id, call_number, call_type, request_payload, response_payload,
       status_code, status, called_at, response_time_ms, error_message
FROM courier_integrations_api_call
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:connection_id = '' OR connection_id = :connection_id)
  AND (:status = '' OR status = :status)
  AND (:call_type = '' OR call_type = :call_type)
ORDER BY called_at DESC
LIMIT :limit;
