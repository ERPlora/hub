-- Tiendas Uber Eats registradas para el hub. Runtime inyecta :hub_id.
-- Portado de UberEatsService.list_stores. :active_only ('1' = solo activas, '' = todas).
SELECT id, store_id, name, status, country, currency, is_active, last_sync_at, settings, created_at
FROM uber_eats_store
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY name ASC;
