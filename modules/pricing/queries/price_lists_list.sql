-- Lista de listas de precios activas del hub. Runtime inyecta :hub_id.
-- Portado de PricingService.list_price_lists (active_only por defecto, orden por code).
SELECT id, code, name, currency, is_default, is_active, valid_from, valid_until, segment
FROM pricing_price_list
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY code ASC;
