-- Transportistas del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de CarriersService.list_carriers. Binds: :active_only (1 = solo activos, 0 = todos),
-- :provider ('' = sin filtro). El campo service_types/max_dimensions van como JSON-TEXT.
SELECT id, code, name, provider, service_types, is_active,
       supports_pickup, supports_tracking, max_weight_kg, max_dimensions
FROM carriers_carrier
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
  AND (:provider = '' OR provider = :provider)
ORDER BY code ASC;
