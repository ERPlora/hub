-- Conexiones de transportista del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de CourierService.list_connections.
-- (:active_only = 1 → solo activas; :courier_code = '' → sin filtro.)
SELECT id, courier_code, name, api_endpoint, account_number, environment,
       is_active, last_call_at, last_call_status, created_at
FROM courier_integrations_connection
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
  AND (:courier_code = '' OR courier_code = :courier_code)
ORDER BY courier_code ASC;
